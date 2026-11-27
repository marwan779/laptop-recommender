namespace Users.Infrastructure.Caching;

public sealed class CacheOptions
{
    public const string SectionName = "Cache";

    public bool Enabled { get; set; } = true;

    /// <summary>
    /// Accepts either a StackExchange.Redis connection string (host:port) or a
    /// redis:// / rediss:// URI such as redis://redis:6379/0.
    /// </summary>
    public string RedisConnectionString { get; set; } = "localhost:6379";

    public int DefaultTtlSeconds { get; set; } = 3600;

    public int ConnectTimeoutMs { get; set; } = 2000;

    public int SyncTimeoutMs { get; set; } = 2000;

    public int ScanPageSize { get; set; } = 100;
}
