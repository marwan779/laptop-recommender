using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Logging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Interfaces.Security;
using Users.Infrastructure.Logging;
using Users.Infrastructure.Messaging;
using Users.Infrastructure.Persistence;
using Users.Infrastructure.Persistence.Repositories;
using Users.Infrastructure.Security;
using Users.Infrastructure.Time;

namespace Users.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        var connectionString = configuration.GetConnectionString("DefaultConnection");
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new InvalidOperationException(
                "Connection string 'DefaultConnection' is not configured. "
                + "For local development, set it with "
                + "'dotnet user-secrets set \"ConnectionStrings:DefaultConnection\" \"<connection-string>\"', "
                + "or set the ConnectionStrings__DefaultConnection environment variable.");
        }

        services.AddDbContext<UsersDbContext>(options =>
            options.UseNpgsql(connectionString));

        services.AddScoped<IUnitOfWork>(sp => sp.GetRequiredService<UsersDbContext>());
        services.AddScoped<IHealthCheckService, DatabaseHealthCheckService>();
        services.AddScoped<IUserRepository, UserRepository>();
        services.AddScoped<IRoleRepository, RoleRepository>();
        services.AddScoped<IRefreshTokenRepository, RefreshTokenRepository>();
        services.AddScoped<IWishlistRepository, WishlistRepository>();
        services.AddScoped<IInboxRepository, InboxRepository>();

        var jwtSection = configuration.GetSection(JwtSettings.SectionName);
        services.Configure<JwtSettings>(options =>
        {
            if (!string.IsNullOrWhiteSpace(jwtSection["Issuer"]))
                options.Issuer = jwtSection["Issuer"]!;
            if (!string.IsNullOrWhiteSpace(jwtSection["Audience"]))
                options.Audience = jwtSection["Audience"]!;
            if (!string.IsNullOrWhiteSpace(jwtSection["SecretKey"]))
                options.SecretKey = jwtSection["SecretKey"]!;
            if (int.TryParse(jwtSection["AccessTokenExpiryMinutes"], out var accessMins))
                options.AccessTokenExpiryMinutes = accessMins;
            if (int.TryParse(jwtSection["RefreshTokenExpiryDays"], out var refreshDays))
                options.RefreshTokenExpiryDays = refreshDays;
        });
        services.AddSingleton<IDateTimeProvider, SystemDateTimeProvider>();
        services.AddSingleton<IPasswordHasher, PasswordHasher>();
        services.AddSingleton<IJwtTokenGenerator, JwtTokenGenerator>();

        services.TryAddSingleton(LoggerConfig.FromEnvironment(configuration));
        services.TryAddSingleton<ILogContextAccessor, AsyncLocalLogContextAccessor>();

        var rabbitSection = configuration.GetSection(RabbitMqOptions.SectionName);
        services.Configure<RabbitMqOptions>(options =>
        {
            if (bool.TryParse(rabbitSection["Enabled"], out var enabled))
                options.Enabled = enabled;
            if (!string.IsNullOrWhiteSpace(rabbitSection["HostName"]))
                options.HostName = rabbitSection["HostName"]!;
            if (int.TryParse(rabbitSection["Port"], out var port))
                options.Port = port;
            if (!string.IsNullOrWhiteSpace(rabbitSection["UserName"]))
                options.UserName = rabbitSection["UserName"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["Password"]))
                options.Password = rabbitSection["Password"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["VirtualHost"]))
                options.VirtualHost = rabbitSection["VirtualHost"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["ExchangeName"]))
                options.ExchangeName = rabbitSection["ExchangeName"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["DlxExchangeName"]))
                options.DlxExchangeName = rabbitSection["DlxExchangeName"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["QueueName"]))
                options.QueueName = rabbitSection["QueueName"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["DlqName"]))
                options.DlqName = rabbitSection["DlqName"]!;
            if (!string.IsNullOrWhiteSpace(rabbitSection["RoutingKey"]))
                options.RoutingKey = rabbitSection["RoutingKey"]!;
            if (ushort.TryParse(rabbitSection["PrefetchCount"], out var prefetch))
                options.PrefetchCount = prefetch;
        });

        services.AddSingleton<LaptopPriceChangedConsumerProcessor>();
        services.AddHostedService<RabbitMqConsumerBackgroundService>();

        return services;
    }
}
