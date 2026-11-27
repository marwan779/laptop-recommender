using Users.Infrastructure.Logging;

namespace Users.Infrastructure.UnitTests.Logging;

public sealed class AsyncLocalLogContextAccessorTests
{
    [Fact]
    public void BeginScope_SetsCorrelationAndMergesContext()
    {
        var accessor = new AsyncLocalLogContextAccessor();

        using (accessor.BeginScope("outer", new Dictionary<string, object?>
               {
                   ["http_method"] = "GET",
                   ["client_ip"] = "127.0.0.1",
               }))
        {
            Assert.Equal("outer", accessor.CorrelationId);
            Assert.Equal("GET", accessor.GetBoundContext()["http_method"]);
            Assert.Equal("127.0.0.1", accessor.GetBoundContext()["client_ip"]);
        }

        Assert.Null(accessor.CorrelationId);
        Assert.Empty(accessor.GetBoundContext());
    }

    [Fact]
    public void NestedScopes_RestorePriorCorrelationAndContext()
    {
        var accessor = new AsyncLocalLogContextAccessor();

        using (accessor.BeginScope("outer", new Dictionary<string, object?> { ["a"] = 1 }))
        {
            using (accessor.BeginScope("inner", new Dictionary<string, object?> { ["b"] = 2 }))
            {
                Assert.Equal("inner", accessor.CorrelationId);
                Assert.Equal(1, accessor.GetBoundContext()["a"]);
                Assert.Equal(2, accessor.GetBoundContext()["b"]);
            }

            Assert.Equal("outer", accessor.CorrelationId);
            Assert.Equal(1, accessor.GetBoundContext()["a"]);
            Assert.False(accessor.GetBoundContext().ContainsKey("b"));
        }

        Assert.Null(accessor.CorrelationId);
        Assert.Empty(accessor.GetBoundContext());
    }

    [Fact]
    public async Task CorrelationAndContext_FlowAcrossAwait()
    {
        var accessor = new AsyncLocalLogContextAccessor();

        using (accessor.BeginScope("async-cid", new Dictionary<string, object?> { ["request"] = "health" }))
        {
            await Task.Yield();

            Assert.Equal("async-cid", accessor.CorrelationId);
            Assert.Equal("health", accessor.GetBoundContext()["request"]);

            await Task.Delay(10);

            Assert.Equal("async-cid", accessor.CorrelationId);
        }

        Assert.Null(accessor.CorrelationId);
    }

    [Fact]
    public void Clear_RemovesCorrelationAndBoundContext()
    {
        var accessor = new AsyncLocalLogContextAccessor();
        using var scope = accessor.BeginScope("cid", new Dictionary<string, object?> { ["k"] = "v" });

        accessor.Clear();

        Assert.Null(accessor.CorrelationId);
        Assert.Empty(accessor.GetBoundContext());
    }
}
