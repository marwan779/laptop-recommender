using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Users.Infrastructure.Logging;

namespace Users.Infrastructure.UnitTests.Logging;

public sealed class LoggerConfigTests
{
    private static IConfiguration BuildConfig(params (string Key, string Value)[] values) =>
        new ConfigurationBuilder()
            .AddInMemoryCollection(values.Select(value =>
                new KeyValuePair<string, string?>(value.Key, value.Value)))
            .Build();

    [Fact]
    public void ServiceNamePrefersServiceNameOverDdService()
    {
        var config = LoggerConfig.FromEnvironment(BuildConfig(
            ("SERVICE_NAME", "users-service-from-config"),
            ("DD_SERVICE", "dd-service")));

        Assert.Equal("users-service-from-config", config.ServiceName);
    }

    [Fact]
    public void FallsBackToDdServiceWhenServiceNameMissing()
    {
        var config = LoggerConfig.FromEnvironment(BuildConfig(
            ("DD_SERVICE", "dd-fallback-service")));

        Assert.Equal("dd-fallback-service", config.ServiceName);
    }

    [Theory]
    [InlineData("Production", "production", true)]
    [InlineData("prod", "production", true)]
    [InlineData("Staging", "staging", true)]
    [InlineData("Testing", "testing", false)]
    [InlineData("Development", "development", false)]
    [InlineData("development", "development", false)]
    public void EnvironmentAliasesNormalizeAndDriveLogFormat(
        string rawEnvironment,
        string expectedEnvironment,
        bool expectJson)
    {
        var config = LoggerConfig.FromEnvironment(BuildConfig(
            ("ASPNETCORE_ENVIRONMENT", rawEnvironment),
            ("APP_VERSION", "2.3.4")));

        Assert.Equal(expectedEnvironment, config.Environment);
        Assert.Equal("2.3.4", config.Version);
        Assert.Equal(expectJson, config.JsonOutput);
    }

    [Fact]
    public void EnvironmentPrecedenceUsesEnvironmentBeforeDdEnv()
    {
        var config = LoggerConfig.FromEnvironment(BuildConfig(
            ("ENVIRONMENT", "staging"),
            ("ENV", "production"),
            ("DD_ENV", "production"),
            ("ASPNETCORE_ENVIRONMENT", "Development")));

        Assert.Equal("staging", config.Environment);
    }

    [Fact]
    public void LogLevelAndFormatOverridesAreApplied()
    {
        var config = LoggerConfig.FromEnvironment(BuildConfig(
            ("ENVIRONMENT", "production"),
            ("LOG_LEVEL", "WARNING"),
            ("LOG_FORMAT", "console")));

        Assert.Equal(LogLevel.Warning, config.MinimumLevel);
        Assert.False(config.JsonOutput);
    }

    [Fact]
    public void DevelopmentDefaultsToDebugAndConsole()
    {
        var previousLogLevel = Environment.GetEnvironmentVariable("LOG_LEVEL");
        var previousLogFormat = Environment.GetEnvironmentVariable("LOG_FORMAT");
        try
        {
            Environment.SetEnvironmentVariable("LOG_LEVEL", null);
            Environment.SetEnvironmentVariable("LOG_FORMAT", null);

            var config = LoggerConfig.FromEnvironment(BuildConfig(
                ("ASPNETCORE_ENVIRONMENT", "Development")));

            Assert.Equal("development", config.Environment);
            Assert.Equal(LogLevel.Debug, config.MinimumLevel);
            Assert.False(config.JsonOutput);
            Assert.Equal("0.1.0", config.Version);
        }
        finally
        {
            Environment.SetEnvironmentVariable("LOG_LEVEL", previousLogLevel);
            Environment.SetEnvironmentVariable("LOG_FORMAT", previousLogFormat);
        }
    }

    [Fact]
    public void ReadsEnvironmentVariablesWhenConfigurationIsMissing()
    {
        var keys = new[]
        {
            "SERVICE_NAME", "DD_SERVICE", "ENVIRONMENT", "ENV", "DD_ENV",
            "ASPNETCORE_ENVIRONMENT", "APP_VERSION", "DD_VERSION", "LOG_LEVEL", "LOG_FORMAT",
        };
        var previous = keys.ToDictionary(key => key, Environment.GetEnvironmentVariable);
        try
        {
            foreach (var key in keys)
            {
                Environment.SetEnvironmentVariable(key, null);
            }

            Environment.SetEnvironmentVariable("DD_SERVICE", "env-users-service");
            Environment.SetEnvironmentVariable("DD_ENV", "production");
            Environment.SetEnvironmentVariable("DD_VERSION", "9.9.9");
            Environment.SetEnvironmentVariable("LOG_LEVEL", "ERROR");
            Environment.SetEnvironmentVariable("LOG_FORMAT", "console");

            var config = LoggerConfig.FromEnvironment();

            Assert.Equal("env-users-service", config.ServiceName);
            Assert.Equal("production", config.Environment);
            Assert.Equal("9.9.9", config.Version);
            Assert.Equal(LogLevel.Error, config.MinimumLevel);
            Assert.False(config.JsonOutput);
        }
        finally
        {
            foreach (var entry in previous)
            {
                Environment.SetEnvironmentVariable(entry.Key, entry.Value);
            }
        }
    }
}
