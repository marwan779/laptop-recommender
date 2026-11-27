namespace Users.Application.Common.Interfaces.Caching;

/// <summary>
/// Transport-agnostic cache abstraction. Implementations must be fail-open:
/// cache outages should never fail the caller.
/// </summary>
public interface ICacheProvider
{
    Task<byte[]?> GetAsync(string key, CancellationToken cancellationToken = default);

    Task SetAsync(
        string key,
        byte[] value,
        int? ttlSeconds = null,
        CancellationToken cancellationToken = default);

    Task DeleteAsync(string key, CancellationToken cancellationToken = default);

    Task<int> ClearPrefixAsync(string prefix, CancellationToken cancellationToken = default);

    Task<bool> HealthCheckAsync(CancellationToken cancellationToken = default);
}
