using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Logging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Interfaces.Security;
using Users.Infrastructure.Logging;
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

        return services;
    }
}
