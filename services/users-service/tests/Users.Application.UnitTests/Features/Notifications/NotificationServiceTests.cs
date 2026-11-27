using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Notifications.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Notifications;

public sealed class NotificationServiceTests
{
    private readonly FakeNotificationRepository _repo = new();
    private readonly FakeUnitOfWork _uow = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 26, 21, 5, 0, DateTimeKind.Utc));
    private readonly FakeCacheProvider _cache = new();
    private readonly NotificationService _sut;

    public NotificationServiceTests()
    {
        _sut = new NotificationService(_repo, _uow, _clock, _cache);
    }

    [Fact]
    public async Task GetMyNotificationsAsync_ReturnsItemsAndUnreadCount()
    {
        var userId = Guid.NewGuid();
        var n1 = Notification.Create(userId, "lap-1", "Drop 1", "Msg 1", "PRICE_DROP");
        var n2 = Notification.Create(userId, "lap-2", "Drop 2", "Msg 2", "PRICE_DROP");
        n2.MarkAsRead(_clock.UtcNow.AddMinutes(-5));
        _repo.Items.AddRange([n1, n2]);

        var result = await _sut.GetMyNotificationsAsync(userId);

        Assert.True(result.IsSuccess);
        Assert.Equal(2, result.Value!.Items.Count);
        Assert.Equal(1, result.Value.UnreadCount);
    }

    [Fact]
    public async Task MarkAsReadAsync_MarksNotificationAndSaves()
    {
        var userId = Guid.NewGuid();
        var n1 = Notification.Create(userId, "lap-1", "Drop 1", "Msg 1", "PRICE_DROP");
        _repo.Items.Add(n1);

        var result = await _sut.MarkAsReadAsync(userId, n1.Id);

        Assert.True(result.IsSuccess);
        Assert.True(result.Value!.IsRead);
        Assert.Equal(_clock.UtcNow, result.Value.ReadAtUtc);
        Assert.Equal(1, _uow.SaveCount);
        Assert.Contains($"users:{userId}:notifications:", _cache.ClearedPrefixes);
    }

    [Fact]
    public async Task MarkAsReadAsync_NotFound_ReturnsNotFound()
    {
        var result = await _sut.MarkAsReadAsync(Guid.NewGuid(), Guid.NewGuid());

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.NotFound, result.ErrorType);
    }

    [Fact]
    public async Task MarkAllAsReadAsync_ReturnsUpdatedCount()
    {
        var userId = Guid.NewGuid();
        _repo.Items.AddRange(
        [
            Notification.Create(userId, "lap-1", "Drop 1", "Msg 1", "PRICE_DROP"),
            Notification.Create(userId, "lap-2", "Drop 2", "Msg 2", "RESTOCK"),
        ]);

        var result = await _sut.MarkAllAsReadAsync(userId);

        Assert.True(result.IsSuccess);
        Assert.Equal(2, result.Value!.MarkedCount);
        Assert.Equal(0, await _repo.GetUnreadCountAsync(userId));
        Assert.Contains($"users:{userId}:notifications:", _cache.ClearedPrefixes);
    }

    private sealed class FakeNotificationRepository : INotificationRepository
    {
        public List<Notification> Items { get; } = [];

        public Task<IReadOnlyList<Notification>> GetByUserIdAsync(
            Guid userId,
            bool unreadOnly = false,
            int limit = 50,
            CancellationToken cancellationToken = default)
        {
            var query = Items.Where(n => n.UserId == userId);
            if (unreadOnly)
            {
                query = query.Where(n => !n.IsRead);
            }

            return Task.FromResult<IReadOnlyList<Notification>>(
                query.OrderByDescending(n => n.CreatedAtUtc).Take(limit).ToList());
        }

        public Task<int> GetUnreadCountAsync(Guid userId, CancellationToken cancellationToken = default)
            => Task.FromResult(Items.Count(n => n.UserId == userId && !n.IsRead));

        public Task<Notification?> GetByIdAndUserIdAsync(Guid id, Guid userId, CancellationToken cancellationToken = default)
            => Task.FromResult(Items.FirstOrDefault(n => n.Id == id && n.UserId == userId));

        public Task<int> MarkAllAsReadAsync(Guid userId, DateTime readAtUtc, CancellationToken cancellationToken = default)
        {
            var unread = Items.Where(n => n.UserId == userId && !n.IsRead).ToList();
            foreach (var n in unread)
            {
                n.MarkAsRead(readAtUtc);
            }

            return Task.FromResult(unread.Count);
        }

        public Task<int> DeleteAllByUserIdAsync(Guid userId, CancellationToken cancellationToken = default)
        {
            var removed = Items.RemoveAll(n => n.UserId == userId);
            return Task.FromResult(removed);
        }

        public Task AddRangeAsync(IEnumerable<Notification> notifications, CancellationToken cancellationToken = default)
        {
            Items.AddRange(notifications);
            return Task.CompletedTask;
        }
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
}
