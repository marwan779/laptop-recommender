using System.Diagnostics;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using Users.Application.Common.Interfaces.Caching;
using Users.Infrastructure.Caching;

namespace Users.Api.Middleware;

/// <summary>
/// Response cache for whitelisted authenticated GET endpoints. Cache keys are
/// scoped by user ID, so responses can never leak between users.
/// Runs after authentication/authorization so the user principal is populated.
/// </summary>
public sealed class ResponseCacheMiddleware(
    RequestDelegate next,
    ICacheProvider cacheProvider,
    IOptions<CacheOptions> options,
    ILogger<ResponseCacheMiddleware> logger)
{
    private readonly CacheOptions _options = options.Value;

    public async Task InvokeAsync(HttpContext context)
    {
        if (!_options.Enabled)
        {
            await next(context);
            return;
        }

        var routePrefix = MatchCacheablePrefix(context.Request.Method, context.Request.Path);
        if (routePrefix is null)
        {
            await next(context);
            return;
        }

        var userId = GetUserId(context.User);
        if (userId is null)
        {
            await next(context);
            return;
        }

        var cacheKey = BuildCacheKey(userId.Value, routePrefix, context.Request);

        var lookupStopwatch = Stopwatch.StartNew();
        var cachedBytes = await cacheProvider.GetAsync(cacheKey, context.RequestAborted);
        lookupStopwatch.Stop();
        var lookupMs = lookupStopwatch.Elapsed.TotalMilliseconds;

        if (cachedBytes is not null)
        {
            logger.LogInformation(
                "Cache HIT for {Method} {Path} [key={CacheKey}, lookup={LookupMs:F2}ms]",
                context.Request.Method,
                context.Request.Path,
                cacheKey,
                lookupMs);

            context.Response.StatusCode = StatusCodes.Status200OK;
            context.Response.ContentType = "application/json; charset=utf-8";
            context.Response.Headers["X-Cache"] = "HIT";
            context.Response.Headers["X-Cache-Key"] = cacheKey;
            context.Response.Headers["X-Cache-Lookup-Time-Ms"] = lookupMs.ToString("F2");
            await context.Response.Body.WriteAsync(cachedBytes, context.RequestAborted);
            return;
        }

        var originalBody = context.Response.Body;
        await using var buffer = new MemoryStream();
        context.Response.Body = buffer;

        try
        {
            await next(context);

            buffer.Position = 0;
            if (context.Response.StatusCode == StatusCodes.Status200OK)
            {
                var responseBytes = buffer.ToArray();
                await cacheProvider.SetAsync(
                    cacheKey,
                    responseBytes,
                    _options.DefaultTtlSeconds,
                    context.RequestAborted);

                context.Response.Headers["X-Cache"] = "MISS";
                context.Response.Headers["X-Cache-Key"] = cacheKey;
                context.Response.Headers["X-Cache-Lookup-Time-Ms"] = lookupMs.ToString("F2");

                logger.LogInformation(
                    "Cache MISS -> stored {Method} {Path} [key={CacheKey}, bytes={Bytes}, ttl={Ttl}s]",
                    context.Request.Method,
                    context.Request.Path,
                    cacheKey,
                    responseBytes.Length,
                    _options.DefaultTtlSeconds);
            }
            else
            {
                context.Response.Headers["X-Cache"] = "MISS";
            }

            await buffer.CopyToAsync(originalBody, context.RequestAborted);
        }
        finally
        {
            context.Response.Body = originalBody;
        }
    }

    private static string? MatchCacheablePrefix(string method, PathString path)
    {
        if (!HttpMethods.IsGet(method))
        {
            return null;
        }

        var normalizedPath = (path.Value ?? string.Empty).TrimEnd('/');

        if (normalizedPath.Equals("/api/v1/users/auth/me", StringComparison.OrdinalIgnoreCase))
        {
            return "profile";
        }

        if (normalizedPath.Equals("/api/v1/users/wishlist", StringComparison.OrdinalIgnoreCase))
        {
            return "wishlist";
        }

        if (normalizedPath.Equals("/api/v1/users/notifications", StringComparison.OrdinalIgnoreCase)
            || normalizedPath.Equals("/api/v1/users/notifications/unread-count", StringComparison.OrdinalIgnoreCase))
        {
            return "notifications";
        }

        return null;
    }

    private static Guid? GetUserId(ClaimsPrincipal user)
    {
        var subject = user.FindFirstValue(ClaimTypes.NameIdentifier)
            ?? user.FindFirstValue("sub");

        return Guid.TryParse(subject, out var userId) ? userId : null;
    }

    private static string BuildCacheKey(Guid userId, string routePrefix, HttpRequest request)
    {
        var fingerprint = $"{request.Method}:{request.Path}{request.QueryString}";
        var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(fingerprint)))
            .ToLowerInvariant();

        return $"users:{userId}:{routePrefix}:{digest}";
    }
}
