using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Feedback.DTOs;
using Users.Application.Features.Feedback.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Feedback;

public sealed class FeedbackServiceTests
{
    private readonly FakeFeedbackRepo _repo = new();
    private readonly FakeUnitOfWork _uow = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 27, 9, 0, 0, DateTimeKind.Utc));
    private readonly FeedbackService _sut;

    public FeedbackServiceTests()
    {
        _sut = new FeedbackService(_repo, _uow, _clock);
    }

    [Fact]
    public async Task SubmitAsync_GuestReport_SavesWithNullUserId()
    {
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
        Assert.Equal(1, _uow.SaveCount);
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
    public async Task ReviewAsync_AdminResolvesReport_SetsStatusNotesAndTimestamp()
    {
        var adminId = Guid.NewGuid();
        var report = FeedbackReport.Create(Guid.NewGuid(), "u@example.com", "WRONG_SPEC", "Wrong RAM", "Says 16GB but 8GB");
        _repo.Items.Add(report);

        var result = await _sut.ReviewAsync(
            adminId,
            report.Id,
            new UpdateFeedbackStatusRequest("RESOLVED", "Corrected spec in catalog"));

        Assert.True(result.IsSuccess);
        Assert.Equal("RESOLVED", result.Value!.Status);
        Assert.Equal("Corrected spec in catalog", result.Value.AdminNotes);
        Assert.Equal(_clock.UtcNow, result.Value.ResolvedAtUtc);
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
}
