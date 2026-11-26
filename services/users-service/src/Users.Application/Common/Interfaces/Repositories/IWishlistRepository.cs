using Users.Domain.Entities;

namespace Users.Application.Common.Interfaces.Repositories;

public interface IWishlistRepository
{
    Task<IReadOnlyList<WishlistItem>> GetByUserIdAsync(Guid userId, CancellationToken cancellationToken = default);
    Task<WishlistItem?> GetByUserAndCanonicalIdAsync(Guid userId, string canonicalId, CancellationToken cancellationToken = default);
    Task<bool> ExistsAsync(Guid userId, string canonicalId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<WishlistItem>> GetSubscribersByCanonicalIdAsync(string canonicalId, CancellationToken cancellationToken = default);
    Task AddAsync(WishlistItem item, CancellationToken cancellationToken = default);
    void Remove(WishlistItem item);
}
