using Microsoft.EntityFrameworkCore;
using Users.Application.Common.Interfaces.Repositories;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Repositories;

public sealed class RefreshTokenRepository(UsersDbContext dbContext) : IRefreshTokenRepository
{
    public async Task<RefreshToken?> GetByTokenHashAsync(string tokenHash, CancellationToken cancellationToken = default)
    {
        return await dbContext.RefreshTokens
            .Include(t => t.User)
            .ThenInclude(u => u!.Role)
            .FirstOrDefaultAsync(t => t.TokenHash == tokenHash, cancellationToken);
    }

    public async Task AddAsync(RefreshToken refreshToken, CancellationToken cancellationToken = default)
    {
        await dbContext.RefreshTokens.AddAsync(refreshToken, cancellationToken);
    }

    public async Task RevokeAllForUserAsync(Guid userId, DateTime utcNow, CancellationToken cancellationToken = default)
    {
        await dbContext.RefreshTokens
            .Where(t => t.UserId == userId && t.RevokedAtUtc == null)
            .ExecuteUpdateAsync(
                setters => setters
                    .SetProperty(t => t.RevokedAtUtc, utcNow)
                    .SetProperty(t => t.UpdatedAtUtc, utcNow),
                cancellationToken);
    }
}
