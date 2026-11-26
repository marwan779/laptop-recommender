namespace Users.Application.Common.Interfaces;

public interface IHealthCheckService
{
    Task<bool> CanConnectToDatabaseAsync(CancellationToken cancellationToken = default);
}
