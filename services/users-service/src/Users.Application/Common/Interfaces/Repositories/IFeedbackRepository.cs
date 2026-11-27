using Users.Domain.Entities;

namespace Users.Application.Common.Interfaces.Repositories;

public interface IFeedbackRepository
{
    Task AddAsync(FeedbackReport report, CancellationToken cancellationToken = default);

    Task<IReadOnlyList<FeedbackReport>> GetByUserIdAsync(
        Guid userId,
        int limit = 50,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<FeedbackReport>> ListAsync(
        string? status = null,
        string? category = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default);

    Task<FeedbackReport?> GetByIdAsync(Guid id, CancellationToken cancellationToken = default);
}
