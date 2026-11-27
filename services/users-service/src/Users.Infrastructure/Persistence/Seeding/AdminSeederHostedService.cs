using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Security;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Seeding;

/// <summary>
/// Idempotently seeds the initial Admin role assignment and first Admin account on startup.
/// </summary>
public sealed class AdminSeederHostedService(
    IServiceScopeFactory scopeFactory,
    IOptions<AdminSeedOptions> options,
    ILogger<AdminSeederHostedService> logger) : IHostedService
{
    private readonly AdminSeedOptions _options = options.Value;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        if (!_options.Enabled)
        {
            return;
        }

        var normalizedEmail = (_options.Email ?? string.Empty).Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(normalizedEmail))
        {
            return;
        }

        try
        {
            using var scope = scopeFactory.CreateScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<UsersDbContext>();
            var passwordHasher = scope.ServiceProvider.GetRequiredService<IPasswordHasher>();
            var dateTimeProvider = scope.ServiceProvider.GetRequiredService<IDateTimeProvider>();

            await EnsureSeedRolesAsync(dbContext, cancellationToken);

            var existingUser = await dbContext.Users
                .FirstOrDefaultAsync(u => u.Email == normalizedEmail, cancellationToken);

            var utcNow = dateTimeProvider.UtcNow;

            if (existingUser is not null)
            {
                var updated = false;
                if (existingUser.RoleId != Role.AdminRoleId)
                {
                    existingUser.ChangeRole(Role.AdminRoleId, utcNow);
                    updated = true;
                }

                if (!existingUser.IsActive)
                {
                    existingUser.Activate(utcNow);
                    updated = true;
                }

                if (!existingUser.EmailVerified)
                {
                    existingUser.VerifyEmail(utcNow);
                    updated = true;
                }

                if (updated)
                {
                    await dbContext.SaveChangesAsync(cancellationToken);
                    logger.LogInformation("Promoted seeded Admin account [email={Email}]", normalizedEmail);
                }

                return;
            }

            if (string.IsNullOrWhiteSpace(_options.Password) || _options.Password.Length < 8)
            {
                logger.LogWarning(
                    "AdminSeed:Password is not configured (min 8 chars); skipping initial Admin user creation for {Email}",
                    normalizedEmail);
                return;
            }

            var passwordHash = passwordHasher.Hash(_options.Password);
            var adminUser = User.Create(
                normalizedEmail,
                _options.FullName,
                passwordHash,
                Role.AdminRoleId,
                "en");
            adminUser.VerifyEmail(utcNow);

            await dbContext.Users.AddAsync(adminUser, cancellationToken);
            await dbContext.SaveChangesAsync(cancellationToken);

            logger.LogInformation("Seeded initial Admin account [email={Email}]", normalizedEmail);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed while running AdminSeederHostedService for {Email}", normalizedEmail);
        }
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    private static async Task EnsureSeedRolesAsync(UsersDbContext dbContext, CancellationToken cancellationToken)
    {
        var hasUserRole = await dbContext.Roles.AnyAsync(r => r.Id == Role.UserRoleId, cancellationToken);
        if (!hasUserRole)
        {
            await dbContext.Roles.AddAsync(
                Role.Create("User", "Standard authenticated shopper account.", Role.UserRoleId),
                cancellationToken);
        }

        var hasAdminRole = await dbContext.Roles.AnyAsync(r => r.Id == Role.AdminRoleId, cancellationToken);
        if (!hasAdminRole)
        {
            await dbContext.Roles.AddAsync(
                Role.Create("Admin", "Administrative account for Users Service management.", Role.AdminRoleId),
                cancellationToken);
        }

        if (!hasUserRole || !hasAdminRole)
        {
            await dbContext.SaveChangesAsync(cancellationToken);
        }
    }
}
