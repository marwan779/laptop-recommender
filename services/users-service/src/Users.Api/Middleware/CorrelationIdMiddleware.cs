using System.Diagnostics;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Logging;

namespace Users.Api.Middleware;

/// <summary>
/// Establishes a correlation ID for every request, binds ambient log context,
/// and emits structured request start/completion/error logs.
/// </summary>
public sealed class CorrelationIdMiddleware(
    RequestDelegate next,
    ILogger<CorrelationIdMiddleware> logger,
    ILogContextAccessor contextAccessor)
{
    private const string HeaderName = "X-Correlation-ID";

    public async Task InvokeAsync(HttpContext context)
    {
        var correlationId = context.Request.Headers[HeaderName].FirstOrDefault()?.Trim();
        if (string.IsNullOrWhiteSpace(correlationId))
        {
            correlationId = Guid.NewGuid().ToString();
        }

        context.TraceIdentifier = correlationId;

        // Set the response header before invoking the pipeline so it survives
        // unhandled exceptions as long as the response has not started.
        if (!context.Response.HasStarted)
        {
            context.Response.Headers[HeaderName] = correlationId;
        }

        var method = context.Request.Method;
        var path = context.Request.Path.HasValue ? context.Request.Path.Value! : "/";
        var clientIp = ResolveClientIp(context);

        var properties = new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["http_method"] = method,
            ["http_path"] = path,
            ["client_ip"] = clientIp,
        };

        var scope = contextAccessor.BeginScope(correlationId, properties);
        var startedAt = Stopwatch.GetTimestamp();

        try
        {
            logger.LogInformation("HTTP {http_method} {http_path} started", method, path);

            await next(context);

            var durationMs = Stopwatch.GetElapsedTime(startedAt).TotalMilliseconds;
            logger.LogInformation(
                "HTTP {http_method} {http_path} completed [status={http_status}, duration={duration_ms:F2}ms]",
                method,
                path,
                context.Response.StatusCode,
                durationMs);
        }
        catch (Exception exception)
        {
            var durationMs = Stopwatch.GetElapsedTime(startedAt).TotalMilliseconds;
            logger.LogError(
                exception,
                "HTTP {http_method} {http_path} unhandled exception: {Message} [duration={duration_ms:F2}ms]",
                method,
                path,
                exception.Message,
                durationMs);
            throw;
        }
        finally
        {
            scope.Dispose();
            contextAccessor.Clear();
        }
    }

    private static string ResolveClientIp(HttpContext context)
    {
        var forwardedFor = context.Request.Headers["X-Forwarded-For"].FirstOrDefault();
        if (!string.IsNullOrWhiteSpace(forwardedFor))
        {
            var first = forwardedFor.Split(',', 2)[0].Trim();
            if (!string.IsNullOrWhiteSpace(first))
            {
                return first;
            }
        }

        return context.Connection.RemoteIpAddress?.ToString() ?? "unknown";
    }
}
