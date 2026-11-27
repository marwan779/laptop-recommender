using System.Text.Json;
using Microsoft.Extensions.Logging;
using Users.Infrastructure.Logging;

namespace Users.Infrastructure.UnitTests.Logging;

public sealed class DatadogJsonLogFormatterTests
{
    private static readonly LoggerConfig Config =
        new("users-service", "production", "1.4.2", LogLevel.Information, true);

    [Fact]
    public void Format_EmitsDatadogSchemaWithCorrelationContextAndError()
    {
        var timestamp = new DateTime(2026, 11, 22, 14, 5, 6, 789, DateTimeKind.Utc);
        var context = new Dictionary<string, object?>
        {
            ["http_method"] = "GET",
            ["http_status"] = 200,
            ["duration_ms"] = 12.34,
        };
        var exception = new InvalidOperationException("boom");

        var json = DatadogJsonLogFormatter.Format(
            timestamp,
            LogLevel.Warning,
            "HTTP GET /health completed",
            Config,
            "Users.Api.Controllers.HealthController",
            "Thread-7",
            "cid-123",
            context,
            exception);

        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        Assert.Equal("2026-11-22T14:05:06.789Z", root.GetProperty("timestamp").GetString());
        Assert.Equal("WARNING", root.GetProperty("status").GetString());
        Assert.Equal("HTTP GET /health completed", root.GetProperty("message").GetString());
        Assert.Equal("users-service", root.GetProperty("service").GetString());
        Assert.Equal("production", root.GetProperty("env").GetString());
        Assert.Equal("1.4.2", root.GetProperty("version").GetString());
        Assert.Equal(
            "Users.Api.Controllers.HealthController",
            root.GetProperty("logger").GetProperty("name").GetString());
        Assert.Equal("Thread-7", root.GetProperty("logger").GetProperty("thread_name").GetString());
        Assert.Equal("cid-123", root.GetProperty("correlation_id").GetString());
        Assert.Equal("GET", root.GetProperty("context").GetProperty("http_method").GetString());
        Assert.Equal(200, root.GetProperty("context").GetProperty("http_status").GetInt32());
        Assert.Equal(12.34, root.GetProperty("context").GetProperty("duration_ms").GetDouble());
        Assert.Equal(
            typeof(InvalidOperationException).FullName,
            root.GetProperty("error").GetProperty("kind").GetString());
        Assert.Equal("boom", root.GetProperty("error").GetProperty("message").GetString());
        Assert.False(string.IsNullOrWhiteSpace(root.GetProperty("error").GetProperty("stack").GetString()));
    }

    [Fact]
    public void Format_OmitsCorrelationContextAndErrorWhenAbsent()
    {
        var json = DatadogJsonLogFormatter.Format(
            DateTime.UtcNow,
            LogLevel.Information,
            "health check",
            Config,
            "Users.Api.Program",
            "Thread-1",
            null,
            null,
            null);

        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        Assert.Equal("INFO", root.GetProperty("status").GetString());
        Assert.False(root.TryGetProperty("correlation_id", out _));
        Assert.False(root.TryGetProperty("context", out _));
        Assert.False(root.TryGetProperty("error", out _));
    }

    [Fact]
    public void Format_OmitsEmptyContextAndUsesErrorStatusForCritical()
    {
        var json = DatadogJsonLogFormatter.Format(
            DateTime.UtcNow,
            LogLevel.Critical,
            "fatal",
            Config,
            "Users.Api.Program",
            "Thread-1",
            "cid",
            new Dictionary<string, object?>(),
            null);

        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        Assert.Equal("ERROR", root.GetProperty("status").GetString());
        Assert.False(root.TryGetProperty("context", out _));
    }
}
