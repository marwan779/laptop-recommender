using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Users.Api.Middleware;
using Users.Application.Common.Interfaces;
using Users.Infrastructure.Caching;

namespace Users.Infrastructure.UnitTests.Caching;

public sealed class ResponseCacheMiddlewareTests
{
    private readonly InMemoryCacheProvider _cache = new(new FixedClock());

    [Fact]
    public async Task Invoke_SecondRequestForSameUser_ReturnsCacheHit()
    {
        var calls = 0;
        var middleware = CreateMiddleware(context =>
        {
            calls++;
            context.Response.StatusCode = StatusCodes.Status200OK;
            context.Response.ContentType = "application/json";
            return context.Response.WriteAsync("{\"items\":[]}");
        });

        var userId = Guid.NewGuid();
        var first = CreateContext(userId);
        await middleware.InvokeAsync(first);
        var second = CreateContext(userId);
        await middleware.InvokeAsync(second);

        Assert.Equal(1, calls);
        Assert.Equal("MISS", first.Response.Headers["X-Cache"]);
        Assert.Equal("HIT", second.Response.Headers["X-Cache"]);
        Assert.False(string.IsNullOrWhiteSpace(second.Response.Headers["X-Cache-Key"]));
        Assert.False(string.IsNullOrWhiteSpace(second.Response.Headers["X-Cache-Lookup-Time-Ms"]));
        Assert.Equal("{\"items\":[]}", ReadBody(second));
    }

    [Fact]
    public async Task Invoke_DifferentUsers_DoNotShareCacheEntries()
    {
        var calls = 0;
        var middleware = CreateMiddleware(context =>
        {
            calls++;
            context.Response.StatusCode = StatusCodes.Status200OK;
            return context.Response.WriteAsync("{}");
        });

        var first = CreateContext(Guid.NewGuid());
        await middleware.InvokeAsync(first);
        var second = CreateContext(Guid.NewGuid());
        await middleware.InvokeAsync(second);

        Assert.Equal(2, calls);
        Assert.Equal("MISS", second.Response.Headers["X-Cache"]);
    }

    [Fact]
    public async Task Invoke_Non200Response_IsNotCached()
    {
        var calls = 0;
        var middleware = CreateMiddleware(context =>
        {
            calls++;
            context.Response.StatusCode = StatusCodes.Status404NotFound;
            return context.Response.WriteAsync("not found");
        });

        var userId = Guid.NewGuid();
        var first = CreateContext(userId);
        await middleware.InvokeAsync(first);
        var second = CreateContext(userId);
        await middleware.InvokeAsync(second);

        Assert.Equal(2, calls);
        Assert.Equal("MISS", second.Response.Headers["X-Cache"]);
    }

    [Fact]
    public async Task Invoke_UnauthenticatedRequest_BypassesCache()
    {
        var calls = 0;
        var middleware = CreateMiddleware(context =>
        {
            calls++;
            context.Response.StatusCode = StatusCodes.Status200OK;
            return context.Response.WriteAsync("{}");
        });

        var first = CreateContext(userId: null);
        await middleware.InvokeAsync(first);
        var second = CreateContext(userId: null);
        await middleware.InvokeAsync(second);

        Assert.Equal(2, calls);
        Assert.False(second.Response.Headers.ContainsKey("X-Cache"));
    }

    [Theory]
    [InlineData("/api/v1/users/auth/me")]
    [InlineData("/api/v1/users/wishlist")]
    [InlineData("/api/v1/users/notifications")]
    [InlineData("/api/v1/users/notifications/unread-count")]
    public async Task Invoke_WhitelistedRoutes_AreCached(string path)
    {
        var calls = 0;
        var middleware = CreateMiddleware(context =>
        {
            calls++;
            context.Response.StatusCode = StatusCodes.Status200OK;
            return context.Response.WriteAsync("{}");
        });

        var userId = Guid.NewGuid();
        await middleware.InvokeAsync(CreateContext(userId, path));
        await middleware.InvokeAsync(CreateContext(userId, path));

        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task Invoke_PostRequest_BypassesCache()
    {
        var calls = 0;
        var middleware = CreateMiddleware(context =>
        {
            calls++;
            context.Response.StatusCode = StatusCodes.Status200OK;
            return context.Response.WriteAsync("{}");
        });

        var userId = Guid.NewGuid();
        await middleware.InvokeAsync(CreateContext(userId, method: HttpMethods.Post));
        await middleware.InvokeAsync(CreateContext(userId, method: HttpMethods.Post));

        Assert.Equal(2, calls);
    }

    private ResponseCacheMiddleware CreateMiddleware(RequestDelegate next)
        => new(
            next,
            _cache,
            Options.Create(new CacheOptions { Enabled = true }),
            NullLogger<ResponseCacheMiddleware>.Instance);

    private static DefaultHttpContext CreateContext(
        Guid? userId,
        string path = "/api/v1/users/wishlist",
        string method = "GET")
    {
        var context = new DefaultHttpContext();
        context.Request.Method = method;
        context.Request.Path = path;
        context.Request.Scheme = "https";
        context.Request.Host = new HostString("localhost");
        context.Response.Body = new MemoryStream();

        if (userId is not null)
        {
            context.User = new ClaimsPrincipal(new ClaimsIdentity(
            [
                new Claim(ClaimTypes.NameIdentifier, userId.Value.ToString()),
            ], "TestAuth"));
        }

        return context;
    }

    private static string ReadBody(HttpContext context)
    {
        context.Response.Body.Position = 0;
        using var reader = new StreamReader(context.Response.Body, leaveOpen: true);
        return reader.ReadToEnd();
    }

    private sealed class FixedClock : IDateTimeProvider
    {
        public DateTime UtcNow => new(2026, 11, 27, 9, 0, 0, DateTimeKind.Utc);
    }
}
