using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Users.Infrastructure.Logging;

public sealed record LoggerConfig(
    string ServiceName,
    string Environment,
    string Version,
    LogLevel MinimumLevel,
    bool JsonOutput)
{
    private const string DefaultServiceName = "users-service";
    private const string DefaultVersion = "0.1.0";

    public static LoggerConfig FromEnvironment(IConfiguration? config = null)
    {
        var serviceName = Read(config, "SERVICE_NAME")
            ?? Read(config, "DD_SERVICE")
            ?? DefaultServiceName;

        var environment = NormalizeEnvironment(
            Read(config, "ENVIRONMENT")
            ?? Read(config, "ENV")
            ?? Read(config, "DD_ENV")
            ?? Read(config, "ASPNETCORE_ENVIRONMENT"));

        var version = Read(config, "APP_VERSION")
            ?? Read(config, "DD_VERSION")
            ?? DefaultVersion;

        var isProductionLike = environment is "production" or "staging";

        var minimumLevel = ParseLogLevel(Read(config, "LOG_LEVEL"))
            ?? (environment == "development" ? LogLevel.Debug : LogLevel.Information);

        var jsonOutput = ParseLogFormat(Read(config, "LOG_FORMAT"))
            ?? isProductionLike;

        return new LoggerConfig(serviceName.Trim(), environment, version.Trim(), minimumLevel, jsonOutput);
    }

    private static string? Read(IConfiguration? config, string key)
    {
        var fromConfig = config?[key];
        if (!string.IsNullOrWhiteSpace(fromConfig))
        {
            return fromConfig;
        }

        var fromEnvironment = System.Environment.GetEnvironmentVariable(key);
        return string.IsNullOrWhiteSpace(fromEnvironment) ? null : fromEnvironment;
    }

    private static string NormalizeEnvironment(string? raw)
    {
        return (raw ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "prod" or "production" => "production",
            "stage" or "staging" => "staging",
            "test" or "testing" => "testing",
            "dev" or "development" => "development",
            _ => "development",
        };
    }

    private static LogLevel? ParseLogLevel(string? raw)
    {
        return (raw ?? string.Empty).Trim().ToUpperInvariant() switch
        {
            "DEBUG" => LogLevel.Debug,
            "INFO" or "INFORMATION" => LogLevel.Information,
            "WARN" or "WARNING" => LogLevel.Warning,
            "ERROR" => LogLevel.Error,
            _ => null,
        };
    }

    private static bool? ParseLogFormat(string? raw)
    {
        return (raw ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "json" => true,
            "console" or "text" => false,
            _ => null,
        };
    }
}
