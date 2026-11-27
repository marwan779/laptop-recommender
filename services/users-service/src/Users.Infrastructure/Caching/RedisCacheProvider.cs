using System.Net.Sockets;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using StackExchange.Redis;
using Users.Application.Common.Interfaces.Caching;

namespace Users.Infrastructure.Caching;

/// <summary>
/// Redis cache backend. Every operation is fail-open: connection failures are
/// logged and translated into cache misses so request handling is never blocked.
/// </summary>
public sealed class RedisCacheProvider(
    IConnectionMultiplexer? connectionMultiplexer,
    IOptions<CacheOptions> options,
    ILogger<RedisCacheProvider> logger) : ICacheProvider
{
    private readonly CacheOptions _options = options.Value;

    public async Task<byte[]?> GetAsync(string key, CancellationToken cancellationToken = default)
    {
        if (connectionMultiplexer is null)
        {
            return MissingConnection<byte[]?>(null);
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            var value = await connectionMultiplexer.GetDatabase().StringGetAsync(key);
            return value.HasValue ? (byte[]?)value : null;
        }
        catch (Exception ex) when (IsCacheFailure(ex))
        {
            LogFailure(ex, nameof(GetAsync), key);
            return null;
        }
    }

    public async Task SetAsync(
        string key,
        byte[] value,
        int? ttlSeconds = null,
        CancellationToken cancellationToken = default)
    {
        if (connectionMultiplexer is null)
        {
            MissingConnection<object?>(null);
            return;
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            var database = connectionMultiplexer.GetDatabase();
            var effectiveTtl = ttlSeconds ?? _options.DefaultTtlSeconds;

            if (effectiveTtl > 0)
            {
                await database.StringSetAsync(key, value, TimeSpan.FromSeconds(effectiveTtl));
            }
            else
            {
                await database.StringSetAsync(key, value);
            }
        }
        catch (Exception ex) when (IsCacheFailure(ex))
        {
            LogFailure(ex, nameof(SetAsync), key);
        }
    }

    public async Task DeleteAsync(string key, CancellationToken cancellationToken = default)
    {
        if (connectionMultiplexer is null)
        {
            MissingConnection<object?>(null);
            return;
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            await connectionMultiplexer.GetDatabase().KeyDeleteAsync(key);
        }
        catch (Exception ex) when (IsCacheFailure(ex))
        {
            LogFailure(ex, nameof(DeleteAsync), key);
        }
    }

    public async Task<int> ClearPrefixAsync(string prefix, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrEmpty(prefix))
        {
            return 0;
        }

        if (connectionMultiplexer is null)
        {
            return MissingConnection(0);
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            var database = connectionMultiplexer.GetDatabase();
            var pattern = $"{prefix}*";
            var keys = new List<RedisKey>();

            foreach (var server in connectionMultiplexer.GetServers())
            {
                if (server.IsReplica || !server.IsConnected)
                {
                    continue;
                }

                await foreach (var key in server
                    .KeysAsync(pattern: pattern, pageSize: _options.ScanPageSize)
                    .WithCancellation(cancellationToken))
                {
                    keys.Add(key);
                }
            }

            if (keys.Count == 0)
            {
                return 0;
            }

            var removed = await database.KeyDeleteAsync(keys.ToArray());
            return (int)removed;
        }
        catch (Exception ex) when (IsCacheFailure(ex))
        {
            LogFailure(ex, nameof(ClearPrefixAsync), prefix);
            return 0;
        }
    }

    public async Task<bool> HealthCheckAsync(CancellationToken cancellationToken = default)
    {
        if (connectionMultiplexer is null)
        {
            return MissingConnection(false);
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            await connectionMultiplexer.GetDatabase().PingAsync();
            return true;
        }
        catch (Exception ex) when (IsCacheFailure(ex))
        {
            LogFailure(ex, nameof(HealthCheckAsync), "health");
            return false;
        }
    }

    private T MissingConnection<T>(T fallback)
    {
        logger.LogDebug("Redis cache connection is unavailable; bypassing cache.");
        return fallback;
    }

    private void LogFailure(Exception exception, string operation, string key)
    {
        logger.LogWarning(
            exception,
            "Redis cache {Operation} failed for key {CacheKey}; continuing without cache.",
            operation,
            key);
    }

    private static bool IsCacheFailure(Exception exception)
        => exception is RedisException
            or TimeoutException
            or SocketException
            or ObjectDisposedException
            or InvalidOperationException;
}
