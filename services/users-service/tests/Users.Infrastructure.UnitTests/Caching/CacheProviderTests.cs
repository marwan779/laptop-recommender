using Microsoft.Extensions.Options;
using NSubstitute;
using StackExchange.Redis;
using Users.Application.Common.Interfaces;
using Users.Infrastructure.Caching;

namespace Users.Infrastructure.UnitTests.Caching;

public sealed class InMemoryCacheProviderTests
{
    private readonly MutableClock _clock = new(new DateTime(2026, 11, 27, 9, 0, 0, DateTimeKind.Utc));
    private readonly InMemoryCacheProvider _sut;

    public InMemoryCacheProviderTests()
    {
        _sut = new InMemoryCacheProvider(_clock);
    }

    [Fact]
    public async Task SetAndGet_RoundTripsBytes()
    {
        var payload = "hello"u8.ToArray();

        await _sut.SetAsync("users:a:wishlist:1", payload);
        var result = await _sut.GetAsync("users:a:wishlist:1");

        Assert.Equal(payload, result);
    }

    [Fact]
    public async Task GetAsync_ExpiredEntry_ReturnsNull()
    {
        await _sut.SetAsync("users:a:wishlist:1", [1, 2, 3], ttlSeconds: 60);

        _clock.UtcNow = _clock.UtcNow.AddSeconds(61);

        Assert.Null(await _sut.GetAsync("users:a:wishlist:1"));
    }

    [Fact]
    public async Task DeleteAsync_RemovesEntry()
    {
        await _sut.SetAsync("key", [1]);

        await _sut.DeleteAsync("key");

        Assert.Null(await _sut.GetAsync("key"));
    }

    [Fact]
    public async Task ClearPrefixAsync_RemovesOnlyMatchingKeys()
    {
        await _sut.SetAsync("users:a:wishlist:1", [1]);
        await _sut.SetAsync("users:a:wishlist:2", [2]);
        await _sut.SetAsync("users:a:notifications:1", [3]);
        await _sut.SetAsync("users:b:wishlist:1", [4]);

        var removed = await _sut.ClearPrefixAsync("users:a:wishlist:");

        Assert.Equal(2, removed);
        Assert.Null(await _sut.GetAsync("users:a:wishlist:1"));
        Assert.Null(await _sut.GetAsync("users:a:wishlist:2"));
        Assert.NotNull(await _sut.GetAsync("users:a:notifications:1"));
        Assert.NotNull(await _sut.GetAsync("users:b:wishlist:1"));
    }

    [Fact]
    public async Task HealthCheckAsync_ReturnsTrue()
    {
        Assert.True(await _sut.HealthCheckAsync());
    }

    private sealed class MutableClock(DateTime utcNow) : IDateTimeProvider
    {
        public DateTime UtcNow { get; set; } = utcNow;
    }
}

public sealed class RedisCacheProviderTests
{
    private static readonly CacheOptions DefaultOptions = new()
    {
        RedisConnectionString = "localhost:6379",
        DefaultTtlSeconds = 60,
        ConnectTimeoutMs = 100,
        SyncTimeoutMs = 100,
        ScanPageSize = 10,
    };

    [Fact]
    public async Task Operations_WhenRedisThrows_ReturnFailOpenDefaults()
    {
        var connection = Substitute.For<IConnectionMultiplexer>();
        connection
            .GetDatabase(Arg.Any<int>(), Arg.Any<object?>())
            .Returns<IDatabase>(_ => throw new RedisConnectionException(
                ConnectionFailureType.UnableToConnect,
                CommandFlags.None,
                "Redis is down",
                null,
                CommandStatus.Unknown));

        var sut = new RedisCacheProvider(
            connection,
            Microsoft.Extensions.Options.Options.Create(DefaultOptions),
            Microsoft.Extensions.Logging.Abstractions.NullLogger<RedisCacheProvider>.Instance);

        Assert.Null(await sut.GetAsync("key"));
        await sut.SetAsync("key", [1, 2, 3]);
        await sut.DeleteAsync("key");
        Assert.Equal(0, await sut.ClearPrefixAsync("prefix:"));
        Assert.False(await sut.HealthCheckAsync());
    }

    [Fact]
    public async Task Operations_WhenConnectionIsUnavailable_ReturnFailOpenDefaults()
    {
        var sut = new RedisCacheProvider(
            null,
            Options.Create(DefaultOptions),
            Microsoft.Extensions.Logging.Abstractions.NullLogger<RedisCacheProvider>.Instance);

        Assert.Null(await sut.GetAsync("key"));
        Assert.Equal(0, await sut.ClearPrefixAsync("prefix:"));
        Assert.False(await sut.HealthCheckAsync());
    }
}
