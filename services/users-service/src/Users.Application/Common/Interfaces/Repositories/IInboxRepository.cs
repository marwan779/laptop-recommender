using Users.Domain.Entities;

namespace Users.Application.Common.Interfaces.Repositories;

public interface IInboxRepository
{
    Task<bool> ExistsAsync(string messageId, CancellationToken cancellationToken = default);
    Task AddAsync(InboxMessage message, CancellationToken cancellationToken = default);
}
