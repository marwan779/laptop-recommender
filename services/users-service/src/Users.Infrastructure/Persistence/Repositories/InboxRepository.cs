using Microsoft.EntityFrameworkCore;
using Users.Application.Common.Interfaces.Repositories;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Repositories;

public sealed class InboxRepository(UsersDbContext dbContext) : IInboxRepository
{
    public async Task<bool> ExistsAsync(string messageId, CancellationToken cancellationToken = default)
    {
        return await dbContext.InboxMessages
            .AsNoTracking()
            .AnyAsync(m => m.MessageId == messageId, cancellationToken);
    }

    public async Task AddAsync(InboxMessage message, CancellationToken cancellationToken = default)
    {
        await dbContext.InboxMessages.AddAsync(message, cancellationToken);
    }
}
