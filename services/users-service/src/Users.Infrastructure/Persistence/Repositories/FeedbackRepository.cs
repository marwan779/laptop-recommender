using Microsoft.EntityFrameworkCore;
using Users.Application.Common.Interfaces.Repositories;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Repositories;

public sealed class FeedbackRepository(UsersDbContext dbContext) : IFeedbackRepository
{
    public async Task AddAsync(FeedbackReport report, CancellationToken cancellationToken = default)
    {
        await dbContext.FeedbackReports.AddAsync(report, cancellationToken);
    }

    public async Task<IReadOnlyList<FeedbackReport>> GetByUserIdAsync(
        Guid userId,
        int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var clampedLimit = Math.Clamp(limit, 1, 100);
        return await dbContext.FeedbackReports
            .AsNoTracking()
            .Where(f => f.UserId == userId)
            .OrderByDescending(f => f.CreatedAtUtc)
            .Take(clampedLimit)
            .ToListAsync(cancellationToken);
    }

    public async Task<IReadOnlyList<FeedbackReport>> ListAsync(
        string? status = null,
        string? category = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default)
    {
        var clampedLimit = Math.Clamp(limit, 1, 100);
        var clampedOffset = Math.Max(0, offset);

        var query = dbContext.FeedbackReports.AsNoTracking().AsQueryable();

        if (!string.IsNullOrWhiteSpace(status))
        {
            var normalizedStatus = status.Trim().ToUpperInvariant();
            query = query.Where(f => f.Status == normalizedStatus);
        }

        if (!string.IsNullOrWhiteSpace(category))
        {
            var normalizedCategory = category.Trim().ToUpperInvariant();
            query = query.Where(f => f.Category == normalizedCategory);
        }

        return await query
            .OrderByDescending(f => f.CreatedAtUtc)
            .Skip(clampedOffset)
            .Take(clampedLimit)
            .ToListAsync(cancellationToken);
    }

    public async Task<FeedbackReport?> GetByIdAsync(Guid id, CancellationToken cancellationToken = default)
    {
        return await dbContext.FeedbackReports
            .FirstOrDefaultAsync(f => f.Id == id, cancellationToken);
    }
}
