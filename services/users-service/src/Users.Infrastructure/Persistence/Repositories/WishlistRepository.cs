using Microsoft.EntityFrameworkCore;
using Users.Application.Common.Interfaces.Repositories;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Repositories;

public sealed class WishlistRepository(UsersDbContext dbContext) : IWishlistRepository
{
    public async Task<IReadOnlyList<WishlistItem>> GetByUserIdAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        return await dbContext.WishlistItems
            .AsNoTracking()
            .Where(w => w.UserId == userId)
            .OrderByDescending(w => w.CreatedAtUtc)
            .ToListAsync(cancellationToken);
    }

    public async Task<WishlistItem?> GetByUserAndCanonicalIdAsync(
        Guid userId,
        string canonicalId,
        CancellationToken cancellationToken = default)
    {
        return await dbContext.WishlistItems
            .FirstOrDefaultAsync(
                w => w.UserId == userId && w.CanonicalId == canonicalId,
                cancellationToken);
    }

    public async Task<bool> ExistsAsync(
        Guid userId,
        string canonicalId,
        CancellationToken cancellationToken = default)
    {
        return await dbContext.WishlistItems
            .AnyAsync(
                w => w.UserId == userId && w.CanonicalId == canonicalId,
                cancellationToken);
    }

    public async Task<IReadOnlyList<WishlistItem>> GetSubscribersByCanonicalIdAsync(
        string canonicalId,
        CancellationToken cancellationToken = default)
    {
        return await dbContext.WishlistItems
            .Include(w => w.User)
            .Where(w => w.CanonicalId == canonicalId && w.User != null && w.User.IsActive)
            .ToListAsync(cancellationToken);
    }

    public async Task AddAsync(WishlistItem item, CancellationToken cancellationToken = default)
    {
        await dbContext.WishlistItems.AddAsync(item, cancellationToken);
    }

    public void Remove(WishlistItem item)
    {
        dbContext.WishlistItems.Remove(item);
    }
}
