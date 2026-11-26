using Users.Application.Common.Interfaces;

namespace Users.Infrastructure.Persistence;

public sealed class DatabaseHealthCheckService(UsersDbContext dbContext) : IHealthCheckService
{
    public async Task<bool> CanConnectToDatabaseAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            return await dbContext.Database.CanConnectAsync(cancellationToken);
        }
        catch
        {
            return false;
        }
    }
}
