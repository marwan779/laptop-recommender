using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Users.Api.Middleware;
using Users.Infrastructure.Logging;

namespace Users.Infrastructure.UnitTests.Logging;

public sealed class CorrelationIdMiddlewareTests
{
    [Fact]
    public async Task InvokeAsync_SetsCorrelationHeaderAndEmitsJsonRequestLogs()
    {
        var writer = new StringWriter();
        var config = new LoggerConfig(
            "users-service",
            "production",
            "0.1.0",
            LogLevel.Debug,
            JsonOutput: true);
        var accessor = new AsyncLocalLogContextAccessor();

        using var provider = new GlobalLoggerProvider(config, accessor, writer);
        using var factory = LoggerFactory.Create(builder =>
        {
            builder.ClearProviders();
            builder.AddProvider(provider);
            builder.SetMinimumLevel(LogLevel.Debug);
        });

        var logger = factory.CreateLogger<CorrelationIdMiddleware>();
        var nextCalled = false;
        var middleware = new CorrelationIdMiddleware(
            context =>
            {
                nextCalled = true;
                context.Response.StatusCode = StatusCodes.Status204NoContent;
                return Task.CompletedTask;
            },
            logger,
            accessor);

        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;
        context.Request.Path = "/health";
        context.Request.Headers["X-Correlation-ID"] = "test-correlation-id";

        await middleware.InvokeAsync(context);

        Assert.True(nextCalled);
        Assert.Equal("test-correlation-id", context.Response.Headers["X-Correlation-ID"].ToString());
        Assert.Null(accessor.CorrelationId);

        var lines = writer.ToString()
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        Assert.Equal(2, lines.Length);

        using var started = JsonDocument.Parse(lines[0]);
        var startedRoot = started.RootElement;
        Assert.Equal("INFO", startedRoot.GetProperty("status").GetString());
        Assert.Equal("users-service", startedRoot.GetProperty("service").GetString());
        Assert.Equal("production", startedRoot.GetProperty("env").GetString());
        Assert.Equal("test-correlation-id", startedRoot.GetProperty("correlation_id").GetString());
        Assert.Contains("HTTP GET /health started", startedRoot.GetProperty("message").GetString());
        Assert.Equal("GET", startedRoot.GetProperty("context").GetProperty("http_method").GetString());
        Assert.Equal("/health", startedRoot.GetProperty("context").GetProperty("http_path").GetString());

        using var completed = JsonDocument.Parse(lines[1]);
        var completedRoot = completed.RootElement;
        Assert.Contains("HTTP GET /health completed", completedRoot.GetProperty("message").GetString());
        Assert.Equal(
            StatusCodes.Status204NoContent,
            completedRoot.GetProperty("context").GetProperty("http_status").GetInt32());
        Assert.True(completedRoot.GetProperty("context").GetProperty("duration_ms").GetDouble() >= 0);
    }

    [Fact]
    public async Task InvokeAsync_GeneratesCorrelationIdWhenHeaderIsMissing()
    {
        var writer = new StringWriter();
        var config = new LoggerConfig("users-service", "development", "0.1.0", LogLevel.Debug, false);
        var accessor = new AsyncLocalLogContextAccessor();

        using var provider = new GlobalLoggerProvider(config, accessor, writer);
        using var factory = LoggerFactory.Create(builder =>
        {
            builder.ClearProviders();
            builder.AddProvider(provider);
            builder.SetMinimumLevel(LogLevel.Debug);
        });

        var middleware = new CorrelationIdMiddleware(
            _ => Task.CompletedTask,
            factory.CreateLogger<CorrelationIdMiddleware>(),
            accessor);

        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;
        context.Request.Path = "/health";

        await middleware.InvokeAsync(context);

        var header = context.Response.Headers["X-Correlation-ID"].ToString();
        Assert.True(Guid.TryParse(header, out _));
        Assert.Contains($"[cid={header}]", writer.ToString());
    }
}
