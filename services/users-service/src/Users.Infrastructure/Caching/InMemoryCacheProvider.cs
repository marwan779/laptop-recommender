using System.Collections.Concurrent;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;

namespace Users.Infrastructure.Caching;

/// <summary>
/// Thread-safe in-process cache used when Redis is disabled or unavailable in tests.
/// </summary>
public sealed class InMemoryCacheProvider(IDateTimeProvider dateTimeProvider) : ICacheProvider
{
    private readonly ConcurrentDictionary<string, CacheEntry> _entries = new(StringComparer.Ordinal);

    public Task<byte[]?> GetAsync(string key, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        if (!_entries.TryGetValue(key, out var entry))
        {
            return Task.FromResult<byte[]?>(null);
        }

        if (entry.ExpiresAtUtc is { } expiresAt && expiresAt <= dateTimeProvider.UtcNow)
        {
            _entries.TryRemove(key, out _);
            return Task.FromResult<byte[]?>(null);
        }

        return Task.FromResult<byte[]?>(entry.Value);
    }

    public Task SetAsync(
        string key,
        byte[] value,
        int? ttlSeconds = null,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        DateTime? expiresAt = ttlSeconds is > 0
            ? dateTimeProvider.UtcNow.AddSeconds(ttlSeconds.Value)
            : null;

        _entries[key] = new CacheEntry(value, expiresAt);
        return Task.CompletedTask;
    }

    public Task DeleteAsync(string key, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        _entries.TryRemove(key, out _);
        return Task.CompletedTask;
    }

    public Task<int> ClearPrefixAsync(string prefix, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        var removed = 0;
        foreach (var key in _entries.Keys)
        {
            if (key.StartsWith(prefix, StringComparison.Ordinal) && _entries.TryRemove(key, out _))
            {
                removed++;
            }
        }

        return Task.FromResult(removed);
    }

    public Task<bool> HealthCheckAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        PurgeExpired();
        return Task.FromResult(true);
    }

    private void PurgeExpired()
    {
        var now = dateTimeProvider.UtcNow;
        foreach (var (key, entry) in _entries)
        {
            if (entry.ExpiresAtUtc is { } expiresAt && expiresAt <= now)
            {
                _entries.TryRemove(key, out _);
            }
        }
    }

    private sealed record CacheEntry(byte[] Value, DateTime? ExpiresAtUtc);
}
