using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Domain.UnitTests;

public sealed class InboxMessageTests
{
    [Fact]
    public void Create_TrimsAndInitializesProperties()
    {
        var now = new DateTime(2026, 11, 26, 20, 15, 0, DateTimeKind.Utc);
        var msg = InboxMessage.Create("  msg-123  ", "  laptop.price.changed.event  ", now);

        Assert.Equal("msg-123", msg.MessageId);
        Assert.Equal("laptop.price.changed.event", msg.RoutingKey);
        Assert.Equal(now, msg.ProcessedAtUtc);
    }

    [Fact]
    public void Create_RejectsBlankMessageIdOrRoutingKey()
    {
        var now = DateTime.UtcNow;
        Assert.Throws<DomainException>(() => InboxMessage.Create(" ", "laptop.price.changed.event", now));
        Assert.Throws<DomainException>(() => InboxMessage.Create("msg-1", " ", now));
    }
}
