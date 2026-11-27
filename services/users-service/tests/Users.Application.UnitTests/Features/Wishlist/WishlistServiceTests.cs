using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Wishlist.DTOs;
using Users.Application.Features.Wishlist.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Wishlist;

public sealed class WishlistServiceTests
{
    private readonly FakeWishlistRepository _repo = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 26, 20, 0, 0, DateTimeKind.Utc));
    private readonly FakeUnitOfWork _uow = new();
    private readonly FakeCacheProvider _cache = new();
    private readonly WishlistService _sut;

    public WishlistServiceTests()
    {
        _sut = new WishlistService(_repo, _clock, _uow, _cache);
    }

    [Fact]
    public async Task AddAsync_SavesNewWishlistItem()
    {
        var userId = Guid.NewGuid();
        var result = await _sut.AddAsync(
            userId,
            new AddWishlistItemRequest("laptop_asus_tuf", "ASUS TUF F16", 69999m));

        Assert.True(result.IsSuccess);
        Assert.Equal("laptop_asus_tuf", result.Value!.CanonicalId);
        Assert.Equal(1, _uow.SaveCount);
        Assert.Single(_repo.Items);
        Assert.Contains($"users:{userId}:wishlist:", _cache.ClearedPrefixes);
    }

    [Fact]
    public async Task AddAsync_DuplicateCanonicalIdForSameUser_ReturnsConflict()
    {
        var userId = Guid.NewGuid();
        await _sut.AddAsync(userId, new AddWishlistItemRequest("laptop_asus_tuf", "ASUS TUF F16", 69999m));

        var duplicate = await _sut.AddAsync(
            userId,
            new AddWishlistItemRequest("laptop_asus_tuf", "ASUS TUF F16", 69999m));

        Assert.True(duplicate.IsFailure);
        Assert.Equal(ErrorType.Conflict, duplicate.ErrorType);
    }

    [Fact]
    public async Task GetMyWishlistAsync_ReturnsOnlyCurrentUsersItems()
    {
        var userA = Guid.NewGuid();
        var userB = Guid.NewGuid();
        await _sut.AddAsync(userA, new AddWishlistItemRequest("laptop_a", "Laptop A", 40000m));
        await _sut.AddAsync(userB, new AddWishlistItemRequest("laptop_b", "Laptop B", 50000m));

        var result = await _sut.GetMyWishlistAsync(userA);

        Assert.True(result.IsSuccess);
        var item = Assert.Single(result.Value!);
        Assert.Equal("laptop_a", item.CanonicalId);
    }

    [Fact]
    public async Task UpdatePreferencesAsync_UpdatesExistingOrReturnsNotFound()
    {
        var userId = Guid.NewGuid();
        await _sut.AddAsync(userId, new AddWishlistItemRequest("laptop_a", "Laptop A", 40000m));

        var updated = await _sut.UpdatePreferencesAsync(
            userId,
            "laptop_a",
            new UpdateWishlistPreferencesRequest(35000m, true, true, false));

        var missing = await _sut.UpdatePreferencesAsync(
            userId,
            "non_existent",
            new UpdateWishlistPreferencesRequest(35000m, true, false, true));

        Assert.True(updated.IsSuccess);
        Assert.Equal(35000m, updated.Value!.TargetPriceEgp);
        Assert.True(updated.Value.NotifyOnAnyChange);
        Assert.True(missing.IsFailure);
        Assert.Equal(ErrorType.NotFound, missing.ErrorType);
        Assert.Contains($"users:{userId}:wishlist:", _cache.ClearedPrefixes);
    }

    [Fact]
    public async Task RemoveByCanonicalIdAsync_RemovesItemOrReturnsNotFound()
    {
        var userId = Guid.NewGuid();
        await _sut.AddAsync(userId, new AddWishlistItemRequest("laptop_a", "Laptop A", 40000m));

        var removed = await _sut.RemoveByCanonicalIdAsync(userId, "laptop_a");
        var removedAgain = await _sut.RemoveByCanonicalIdAsync(userId, "laptop_a");

        Assert.True(removed.IsSuccess);
        Assert.Empty(_repo.Items);
        Assert.True(removedAgain.IsFailure);
        Assert.Equal(ErrorType.NotFound, removedAgain.ErrorType);
        Assert.Contains($"users:{userId}:wishlist:", _cache.ClearedPrefixes);
    }

    private sealed class FakeWishlistRepository : IWishlistRepository
    {
        public List<WishlistItem> Items { get; } = [];

        public Task<IReadOnlyList<WishlistItem>> GetByUserIdAsync(Guid userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<WishlistItem>>(Items.Where(w => w.UserId == userId).ToList());

        public Task<WishlistItem?> GetByUserAndCanonicalIdAsync(
            Guid userId,
            string canonicalId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(w => w.UserId == userId && w.CanonicalId == canonicalId));

        public Task<bool> ExistsAsync(Guid userId, string canonicalId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.Any(w => w.UserId == userId && w.CanonicalId == canonicalId));

        public Task<IReadOnlyList<WishlistItem>> GetSubscribersByCanonicalIdAsync(
            string canonicalId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<WishlistItem>>(Items.Where(w => w.CanonicalId == canonicalId).ToList());

        public Task AddAsync(WishlistItem item, CancellationToken cancellationToken = default)
        {
            Items.Add(item);
            return Task.CompletedTask;
        }

        public void Remove(WishlistItem item) => Items.Remove(item);
    }

    private sealed class FakeClock(DateTime utcNow) : IDateTimeProvider
    {
        public DateTime UtcNow { get; } = utcNow;
    }

    private sealed class FakeCacheProvider : ICacheProvider
    {
        public List<string> ClearedPrefixes { get; } = [];

        public Task<byte[]?> GetAsync(string key, CancellationToken cancellationToken = default)
            => Task.FromResult<byte[]?>(null);

        public Task SetAsync(string key, byte[] value, int? ttlSeconds = null, CancellationToken cancellationToken = default)
            => Task.CompletedTask;

        public Task DeleteAsync(string key, CancellationToken cancellationToken = default)
            => Task.CompletedTask;

        public Task<int> ClearPrefixAsync(string prefix, CancellationToken cancellationToken = default)
        {
            ClearedPrefixes.Add(prefix);
            return Task.FromResult(1);
        }

        public Task<bool> HealthCheckAsync(CancellationToken cancellationToken = default)
            => Task.FromResult(true);
    }

    private sealed class FakeUnitOfWork : IUnitOfWork
    {
        public int SaveCount { get; private set; }
        public Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
        {
            SaveCount++;
            return Task.FromResult(1);
        }
    }
}
