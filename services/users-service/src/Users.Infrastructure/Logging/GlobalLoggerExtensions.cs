using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Logging;

namespace Users.Infrastructure.Logging;

public static class GlobalLoggerExtensions
{
    /// <summary>
    /// Replaces default logging providers with the users-service global structured logger.
    /// </summary>
    public static ILoggingBuilder AddGlobalLogger(
        this ILoggingBuilder logging,
        IConfiguration configuration)
    {
        var config = LoggerConfig.FromEnvironment(configuration);

        logging.ClearProviders();
        logging.SetMinimumLevel(config.MinimumLevel);

        logging.Services.TryAddSingleton(config);
        logging.Services.TryAddSingleton<ILogContextAccessor, AsyncLocalLogContextAccessor>();
        logging.Services.TryAddEnumerable(ServiceDescriptor.Singleton<ILoggerProvider, GlobalLoggerProvider>());

        return logging;
    }
}
