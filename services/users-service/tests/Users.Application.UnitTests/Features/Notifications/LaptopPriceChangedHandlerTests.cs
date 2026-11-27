using Microsoft.Extensions.Logging.Abstractions;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Features.Notifications.Events;
using Users.Application.Features.Notifications.Handlers;
using Users.Application.Features.Notifications.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Notifications;

public sealed class LaptopPriceChangedHandlerTests
{
    private readonly FakeWishlistRepo _wishlistRepo = new();
    private readonly FakeNotificationRepo _notificationRepo = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 26, 21, 0, 0, DateTimeKind.Utc));
    private readonly AffectedUserTracker _tracker = new();
    private readonly LaptopPriceChangedHandler _sut;

    public LaptopPriceChangedHandlerTests()
    {
        _sut = new LaptopPriceChangedHandler(
            _wishlistRepo,
            _notificationRepo,
            _clock,
            _tracker,
            NullLogger<LaptopPriceChangedHandler>.Instance);
    }

    [Fact]
    public async Task HandleAsync_PriceDrop_NotifiesOnlyMatchingSubscribers()
    {
        var userNoTarget = Guid.NewGuid();
        var userTargetMet = Guid.NewGuid();
        var userTargetNotMet = Guid.NewGuid();
        var userDisabled = Guid.NewGuid();

        _wishlistRepo.Subscribers.AddRange(
        [
            WishlistItem.Create(userNoTarget, "laptop_tuf", "ASUS TUF", 73500m, targetPriceEgp: null, notifyOnPriceDrop: true),
            WishlistItem.Create(userTargetMet, "laptop_tuf", "ASUS TUF", 73500m, targetPriceEgp: 70000m, notifyOnPriceDrop: true),
            WishlistItem.Create(userTargetNotMet, "laptop_tuf", "ASUS TUF", 73500m, targetPriceEgp: 65000m, notifyOnPriceDrop: true),
            WishlistItem.Create(userDisabled, "laptop_tuf", "ASUS TUF", 73500m, notifyOnPriceDrop: false),
        ]);

        var evt = WrapBatch("msg-1", new LaptopPriceChangedEvent(
            "laptop_tuf",
            "ASUS TUF Gaming F16",
            73500m,
            69999m,
            "2B Egypt",
            true,
            "PRICE_DROP"));

        await _sut.HandleAsync(evt, "msg-1");

        Assert.Equal(2, _notificationRepo.Added.Count);
        Assert.Contains(_notificationRepo.Added, n => n.UserId == userNoTarget && n.ChangeType == "PRICE_DROP");
        Assert.Contains(_notificationRepo.Added, n => n.UserId == userTargetMet && n.NewPriceEgp == 69999m);
        Assert.Equal(69999m, _wishlistRepo.Subscribers[0].LastNotifiedPriceEgp);
        Assert.Null(_wishlistRepo.Subscribers[2].LastNotifiedPriceEgp);
        Assert.Equal(
            new[] { userNoTarget, userTargetMet }.OrderBy(id => id),
            _tracker.Snapshot().OrderBy(id => id));
    }

    [Fact]
    public async Task HandleAsync_Restock_NotifiesRestockSubscribers()
    {
        var userRestock = Guid.NewGuid();
        var userNoRestock = Guid.NewGuid();

        _wishlistRepo.Subscribers.AddRange(
        [
            WishlistItem.Create(userRestock, "laptop_legion", "Lenovo Legion", 80000m, notifyOnPriceDrop: false, notifyOnRestock: true),
            WishlistItem.Create(userNoRestock, "laptop_legion", "Lenovo Legion", 80000m, notifyOnPriceDrop: true, notifyOnRestock: false),
        ]);

        var evt = WrapBatch("msg-2", new LaptopPriceChangedEvent(
            "laptop_legion",
            "Lenovo Legion 5",
            80000m,
            80000m,
            "B.TECH",
            true,
            "RESTOCK"));

        await _sut.HandleAsync(evt, "msg-2");

        var created = Assert.Single(_notificationRepo.Added);
        Assert.Equal(userRestock, created.UserId);
        Assert.Equal("RESTOCK", created.ChangeType);
        Assert.Contains("back in stock", created.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Equal([userRestock], _tracker.Snapshot());
    }

    [Fact]
    public async Task HandleAsync_PriceIncrease_NotifiesOnlyNotifyOnAnyChangeSubscribers()
    {
        var userAny = Guid.NewGuid();
        var userDropOnly = Guid.NewGuid();

        _wishlistRepo.Subscribers.AddRange(
        [
            WishlistItem.Create(userAny, "laptop_hp", "HP Victus", 45000m, notifyOnPriceDrop: true, notifyOnAnyChange: true),
            WishlistItem.Create(userDropOnly, "laptop_hp", "HP Victus", 45000m, notifyOnPriceDrop: true, notifyOnAnyChange: false),
        ]);

        var evt = WrapBatch("msg-3", new LaptopPriceChangedEvent(
            "laptop_hp",
            "HP Victus 16",
            45000m,
            48000m,
            "CompuMarts",
            true,
            "PRICE_INCREASE"));

        await _sut.HandleAsync(evt, "msg-3");

        var created = Assert.Single(_notificationRepo.Added);
        Assert.Equal(userAny, created.UserId);
    }

    private static LaptopPriceChangedBatchEvent WrapBatch(string msgId, params LaptopPriceChangedEvent[] changes)
        => new(
            msgId,
            "laptop.price.changed.event",
            "2026-11-27T08:00:00Z",
            "corr-test",
            new LaptopPriceChangedBatchPayload("batch-1", "twob", changes));

    private sealed class FakeWishlistRepo : IWishlistRepository
    {
        public List<WishlistItem> Subscribers { get; } = [];
        public Task<IReadOnlyList<WishlistItem>> GetByUserIdAsync(Guid userId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<WishlistItem>>([]);
        public Task<WishlistItem?> GetByUserAndCanonicalIdAsync(Guid userId, string canonicalId, CancellationToken cancellationToken = default) => Task.FromResult<WishlistItem?>(null);
        public Task<bool> ExistsAsync(Guid userId, string canonicalId, CancellationToken cancellationToken = default) => Task.FromResult(false);
        public Task<IReadOnlyList<WishlistItem>> GetSubscribersByCanonicalIdAsync(string canonicalId, CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<WishlistItem>>(Subscribers.Where(s => s.CanonicalId == canonicalId).ToList());
        public Task AddAsync(WishlistItem item, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public void Remove(WishlistItem item) { }
    }

    private sealed class FakeNotificationRepo : INotificationRepository
    {
        public List<Notification> Added { get; } = [];
        public Task<IReadOnlyList<Notification>> GetByUserIdAsync(Guid userId, bool unreadOnly = false, int limit = 50, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<Notification>>([]);
        public Task<int> GetUnreadCountAsync(Guid userId, CancellationToken cancellationToken = default) => Task.FromResult(0);
        public Task<Notification?> GetByIdAndUserIdAsync(Guid id, Guid userId, CancellationToken cancellationToken = default) => Task.FromResult<Notification?>(null);
        public Task<int> MarkAllAsReadAsync(Guid userId, DateTime readAtUtc, CancellationToken cancellationToken = default) => Task.FromResult(0);
        public Task AddRangeAsync(IEnumerable<Notification> notifications, CancellationToken cancellationToken = default)
        {
            Added.AddRange(notifications);
            return Task.CompletedTask;
        }
    }

    private sealed class FakeClock(DateTime utcNow) : IDateTimeProvider
    {
        public DateTime UtcNow { get; } = utcNow;
    }
}
