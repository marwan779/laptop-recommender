using Hangfire;
using Hangfire.PostgreSql;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using StackExchange.Redis;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Email;
using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Common.Interfaces.Logging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Interfaces.Security;
using Users.Infrastructure.Caching;
using Users.Infrastructure.Email;
using Users.Infrastructure.Jobs;
using Users.Infrastructure.Logging;
using Users.Infrastructure.Messaging;
using Users.Infrastructure.Persistence;
using Users.Infrastructure.Persistence.Repositories;
using Users.Infrastructure.Persistence.Seeding;
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
        services.AddScoped<INotificationRepository, NotificationRepository>();
        services.AddScoped<IFeedbackRepository, FeedbackRepository>();

        var adminSeedSection = configuration.GetSection(AdminSeedOptions.SectionName);
        services.Configure<AdminSeedOptions>(options =>
        {
            if (bool.TryParse(adminSeedSection["Enabled"], out var seedEnabled))
                options.Enabled = seedEnabled;
            if (!string.IsNullOrWhiteSpace(adminSeedSection["Email"]))
                options.Email = adminSeedSection["Email"]!;
            if (!string.IsNullOrWhiteSpace(adminSeedSection["FullName"]))
                options.FullName = adminSeedSection["FullName"]!;
            if (!string.IsNullOrWhiteSpace(adminSeedSection["Password"]))
                options.Password = adminSeedSection["Password"]!;
        });
        services.AddHostedService<AdminSeederHostedService>();

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

        var cacheSection = configuration.GetSection(CacheOptions.SectionName);
        var cacheOptions = new CacheOptions();
        if (bool.TryParse(cacheSection["Enabled"], out var cacheEnabled))
            cacheOptions.Enabled = cacheEnabled;
        if (!string.IsNullOrWhiteSpace(cacheSection["RedisConnectionString"]))
            cacheOptions.RedisConnectionString = cacheSection["RedisConnectionString"]!;
        if (int.TryParse(cacheSection["DefaultTtlSeconds"], out var cacheTtl))
            cacheOptions.DefaultTtlSeconds = cacheTtl;
        if (int.TryParse(cacheSection["ConnectTimeoutMs"], out var connectTimeout))
            cacheOptions.ConnectTimeoutMs = connectTimeout;
        if (int.TryParse(cacheSection["SyncTimeoutMs"], out var syncTimeout))
            cacheOptions.SyncTimeoutMs = syncTimeout;
        if (int.TryParse(cacheSection["ScanPageSize"], out var scanPageSize))
            cacheOptions.ScanPageSize = scanPageSize;

        services.AddSingleton(Options.Create(cacheOptions));

        if (cacheOptions.Enabled && !string.IsNullOrWhiteSpace(cacheOptions.RedisConnectionString))
        {
            services.AddSingleton<IConnectionMultiplexer>(serviceProvider =>
            {
                try
                {
                    return ConnectionMultiplexer.Connect(BuildRedisConfiguration(cacheOptions));
                }
                catch (Exception ex)
                {
                    serviceProvider
                        .GetRequiredService<ILogger<RedisCacheProvider>>()
                        .LogWarning(
                            ex,
                            "Unable to connect to Redis at startup; cache operations will be bypassed until it recovers.");
                    return null!;
                }
            });
            services.AddSingleton<ICacheProvider, RedisCacheProvider>();
        }
        else
        {
            services.AddSingleton<ICacheProvider, InMemoryCacheProvider>();
        }

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

        var emailSection = configuration.GetSection(EmailOptions.SectionName);
        services.Configure<EmailOptions>(options =>
        {
            if (bool.TryParse(emailSection["Enabled"], out var emailEnabled))
                options.Enabled = emailEnabled;
            if (!string.IsNullOrWhiteSpace(emailSection["SmtpHost"]))
                options.SmtpHost = emailSection["SmtpHost"]!;
            if (int.TryParse(emailSection["SmtpPort"], out var smtpPort))
                options.SmtpPort = smtpPort;
            if (bool.TryParse(emailSection["UseStartTls"], out var useStartTls))
                options.UseStartTls = useStartTls;
            if (!string.IsNullOrWhiteSpace(emailSection["UserName"]))
                options.UserName = emailSection["UserName"]!;
            if (!string.IsNullOrWhiteSpace(emailSection["Password"]))
                options.Password = emailSection["Password"]!;
            if (!string.IsNullOrWhiteSpace(emailSection["FromEmail"]))
                options.FromEmail = emailSection["FromEmail"]!;
            if (!string.IsNullOrWhiteSpace(emailSection["FromName"]))
                options.FromName = emailSection["FromName"]!;
        });

        services.AddTransient<IEmailSender, SmtpEmailSender>();
        services.AddTransient<SendPriceAlertEmailJob>();
        services.AddScoped<IBackgroundJobScheduler, HangfireJobScheduler>();

        var hangfireEnabled = !bool.TryParse(configuration["Hangfire:Enabled"], out var hfEnabled) || hfEnabled;
        if (hangfireEnabled)
        {
            services.AddHangfire(config => config
                .SetDataCompatibilityLevel(CompatibilityLevel.Version_180)
                .UseSimpleAssemblyNameTypeSerializer()
                .UseRecommendedSerializerSettings()
                .UsePostgreSqlStorage(
                    options => options.UseNpgsqlConnection(connectionString),
                    new PostgreSqlStorageOptions
                    {
                        SchemaName = "hangfire",
                        PrepareSchemaIfNecessary = true,
                    }));

            services.AddHangfireServer(options =>
            {
                options.ServerName = "users-service-worker";
                options.WorkerCount = 2;
            });
        }

        return services;
    }

    private static ConfigurationOptions BuildRedisConfiguration(CacheOptions options)
    {
        var connectionString = options.RedisConnectionString.Trim();

        ConfigurationOptions configuration;
        if (Uri.TryCreate(connectionString, UriKind.Absolute, out var uri)
            && (uri.Scheme == "redis" || uri.Scheme == "rediss"))
        {
            var port = uri.Port > 0 ? uri.Port : 6379;
            configuration = new ConfigurationOptions
            {
                AbortOnConnectFail = false,
                Ssl = uri.Scheme == "rediss",
                ConnectTimeout = options.ConnectTimeoutMs,
                SyncTimeout = options.SyncTimeoutMs,
                ClientName = "users-service",
            };

            configuration.EndPoints.Add(uri.Host, port);

            var databasePath = uri.AbsolutePath.Trim('/');
            if (int.TryParse(databasePath, out var database))
            {
                configuration.DefaultDatabase = database;
            }

            if (!string.IsNullOrEmpty(uri.UserInfo))
            {
                var separator = uri.UserInfo.IndexOf(':');
                var username = separator >= 0 ? uri.UserInfo[..separator] : uri.UserInfo;
                var password = separator >= 0 ? uri.UserInfo[(separator + 1)..] : null;

                if (!string.IsNullOrEmpty(username))
                {
                    configuration.User = Uri.UnescapeDataString(username);
                }

                if (!string.IsNullOrEmpty(password))
                {
                    configuration.Password = Uri.UnescapeDataString(password);
                }
            }
        }
        else
        {
            configuration = ConfigurationOptions.Parse(connectionString);
            configuration.AbortOnConnectFail = false;
            configuration.ConnectTimeout = options.ConnectTimeoutMs;
            configuration.SyncTimeout = options.SyncTimeoutMs;
            configuration.ClientName = "users-service";
        }

        return configuration;
    }
}
