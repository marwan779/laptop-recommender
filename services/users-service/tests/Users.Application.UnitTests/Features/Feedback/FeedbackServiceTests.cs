using Microsoft.Extensions.Logging.Abstractions;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Feedback.DTOs;
using Users.Application.Features.Feedback.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Feedback;

public sealed class FeedbackServiceTests
{
    private readonly FakeFeedbackRepo _repo = new();
    private readonly FakeUserRepo _userRepo = new();
    private readonly FakeNotificationRepo _notifRepo = new();
    private readonly FakeUnitOfWork _uow = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 27, 9, 0, 0, DateTimeKind.Utc));
    private readonly FakeCache _cache = new();
    private readonly SpyJobScheduler _scheduler = new();
    private readonly FeedbackService _sut;

    public FeedbackServiceTests()
    {
        _sut = new FeedbackService(
            _repo,
            _userRepo,
            _notifRepo,
            _uow,
            _clock,
            _cache,
            _scheduler,
            NullLogger<FeedbackService>.Instance);
    }

    [Fact]
    public async Task SubmitAsync_GuestReport_SavesAndNotifiesAdmins()
    {
        var admin = User.Create("marwanmohamed3337@gmail.com", "Marwan", "hash", Role.AdminRoleId);
        _userRepo.Users.Add(admin);

        var result = await _sut.SubmitAsync(
            null,
            null,
            new CreateFeedbackRequest(
                "WRONG_PRICE",
                "Price mismatch on CompuMarts",
                "Site says 40,600 EGP but store is 39,000 EGP",
                ReporterEmail: "guest@example.com",
                CanonicalId: "laptop_lenovo_loq"));

        Assert.True(result.IsSuccess);
        Assert.Null(result.Value!.UserId);
        Assert.Equal("guest@example.com", result.Value.ReporterEmail);
        Assert.Equal("OPEN", result.Value.Status);
        var adminNotif = Assert.Single(_notifRepo.Items);
        Assert.Equal(admin.Id, adminNotif.UserId);
        Assert.Equal("FEEDBACK_NEW", adminNotif.ChangeType);
        var adminEmail = Assert.Single(_scheduler.AdminEmails);
        Assert.Equal("marwanmohamed3337@gmail.com", adminEmail.ToEmail);
    }

    [Fact]
    public async Task SubmitAsync_AuthenticatedUser_UsesAuthenticatedEmailAndReturnsInMine()
    {
        var userId = Guid.NewGuid();
        var submit = await _sut.SubmitAsync(
            userId,
            "buyer@example.com",
            new CreateFeedbackRequest("UI_BUG", "Button clipped", "Happens on mobile"));

        var mine = await _sut.GetMyReportsAsync(userId);

        Assert.True(submit.IsSuccess);
        Assert.True(mine.IsSuccess);
        var report = Assert.Single(mine.Value!);
        Assert.Equal(userId, report.UserId);
        Assert.Equal("buyer@example.com", report.ReporterEmail);
    }

    [Fact]
    public async Task ReviewAsync_AdminResolvesReport_NotifiesUserByNotificationAndEmail()
    {
        var reporter = User.Create("u@example.com", "Buyer", "hash", Role.UserRoleId, "en");
        _userRepo.Users.Add(reporter);
        var report = FeedbackReport.Create(reporter.Id, reporter.Email, "WRONG_SPEC", "Wrong RAM", "Says 16GB but 8GB");
        _repo.Items.Add(report);

        var result = await _sut.ReviewAsync(
            Guid.NewGuid(),
            report.Id,
            new UpdateFeedbackStatusRequest("RESOLVED", "Corrected spec in catalog"));

        Assert.True(result.IsSuccess);
        Assert.Equal("RESOLVED", result.Value!.Status);
        Assert.Equal("Corrected spec in catalog", result.Value.AdminNotes);
        Assert.Equal(_clock.UtcNow, result.Value.ResolvedAtUtc);
        var userNotif = Assert.Single(_notifRepo.Items);
        Assert.Equal(reporter.Id, userNotif.UserId);
        Assert.Equal("FEEDBACK_RESOLVED", userNotif.ChangeType);
        var email = Assert.Single(_scheduler.ReviewedEmails);
        Assert.Equal("u@example.com", email.ToEmail);
        Assert.Equal("RESOLVED", email.Status);
    }

    [Fact]
    public async Task ReviewAsync_NotFound_ReturnsNotFound()
    {
        var result = await _sut.ReviewAsync(
            Guid.NewGuid(),
            Guid.NewGuid(),
            new UpdateFeedbackStatusRequest("RESOLVED"));

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.NotFound, result.ErrorType);
    }

    private sealed class FakeFeedbackRepo : IFeedbackRepository
    {
        public List<FeedbackReport> Items { get; } = [];
        public Task AddAsync(FeedbackReport report, CancellationToken cancellationToken = default)
        {
            Items.Add(report);
            return Task.CompletedTask;
        }
        public Task<IReadOnlyList<FeedbackReport>> GetByUserIdAsync(Guid userId, int limit = 50, CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<FeedbackReport>>(Items.Where(f => f.UserId == userId).ToList());
        public Task<IReadOnlyList<FeedbackReport>> ListAsync(string? status = null, string? category = null, int limit = 50, int offset = 0, CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<FeedbackReport>>(Items);
        public Task<FeedbackReport?> GetByIdAsync(Guid id, CancellationToken cancellationToken = default)
            => Task.FromResult(Items.FirstOrDefault(f => f.Id == id));
    }

    private sealed class FakeUserRepo : IUserRepository
    {
        public List<User> Users { get; } = [];
        public Task<User?> GetByIdWithRoleAsync(Guid id, CancellationToken cancellationToken = default) => Task.FromResult(Users.FirstOrDefault(u => u.Id == id));
        public Task<User?> GetByEmailWithRoleAsync(string normalizedEmail, CancellationToken cancellationToken = default) => Task.FromResult(Users.FirstOrDefault(u => u.Email == normalizedEmail));
        public Task<bool> ExistsByEmailAsync(string normalizedEmail, CancellationToken cancellationToken = default) => Task.FromResult(Users.Any(u => u.Email == normalizedEmail));
        public Task<IReadOnlyList<User>> ListWithRolesAsync(string? search = null, int limit = 50, int offset = 0, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<User>>(Users);
        public Task<IReadOnlyList<User>> ListActiveAdminsAsync(CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<User>>(Users.Where(u => u.IsActive && u.RoleId == Role.AdminRoleId).ToList());
        public Task<int> CountActiveAdminsAsync(CancellationToken cancellationToken = default) => Task.FromResult(Users.Count(u => u.IsActive && u.RoleId == Role.AdminRoleId));
        public Task AddAsync(User user, CancellationToken cancellationToken = default) { Users.Add(user); return Task.CompletedTask; }
    }

    private sealed class FakeNotificationRepo : INotificationRepository
    {
        public List<Notification> Items { get; } = [];
        public Task<IReadOnlyList<Notification>> GetByUserIdAsync(Guid userId, bool unreadOnly = false, int limit = 50, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<Notification>>([]);
        public Task<int> GetUnreadCountAsync(Guid userId, CancellationToken cancellationToken = default) => Task.FromResult(0);
        public Task<Notification?> GetByIdAndUserIdAsync(Guid id, Guid userId, CancellationToken cancellationToken = default) => Task.FromResult<Notification?>(null);
        public Task<int> MarkAllAsReadAsync(Guid userId, DateTime readAtUtc, CancellationToken cancellationToken = default) => Task.FromResult(0);
        public Task<int> DeleteAllByUserIdAsync(Guid userId, CancellationToken cancellationToken = default) => Task.FromResult(0);
        public Task AddRangeAsync(IEnumerable<Notification> notifications, CancellationToken cancellationToken = default)
        {
            Items.AddRange(notifications);
            return Task.CompletedTask;
        }
    }

    private sealed class FakeUnitOfWork : IUnitOfWork
    {
        public Task<int> SaveChangesAsync(CancellationToken cancellationToken = default) => Task.FromResult(1);
    }

    private sealed class FakeClock(DateTime utcNow) : IDateTimeProvider
    {
        public DateTime UtcNow { get; } = utcNow;
    }

    private sealed class FakeCache : ICacheProvider
    {
        public Task<byte[]?> GetAsync(string key, CancellationToken cancellationToken = default) => Task.FromResult<byte[]?>(null);
        public Task SetAsync(string key, byte[] value, int? ttlSeconds = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task DeleteAsync(string key, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<int> ClearPrefixAsync(string prefix, CancellationToken cancellationToken = default) => Task.FromResult(1);
        public Task<bool> HealthCheckAsync(CancellationToken cancellationToken = default) => Task.FromResult(true);
    }

    private sealed class SpyJobScheduler : IBackgroundJobScheduler
    {
        public List<FeedbackAdminAlertEmailPayload> AdminEmails { get; } = [];
        public List<FeedbackReviewedEmailPayload> ReviewedEmails { get; } = [];
        public string EnqueuePriceAlertEmail(PriceAlertEmailJobPayload payload) => "job-price";
        public string EnqueueFeedbackAdminAlertEmail(FeedbackAdminAlertEmailPayload payload) { AdminEmails.Add(payload); return "job-admin"; }
        public string EnqueueFeedbackReviewedEmail(FeedbackReviewedEmailPayload payload) { ReviewedEmails.Add(payload); return "job-user"; }
    }
}
