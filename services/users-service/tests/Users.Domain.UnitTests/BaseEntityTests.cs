using Users.Domain.Common;

namespace Users.Domain.UnitTests;

public sealed class BaseEntityTests
{
    private sealed class TestEntity : BaseEntity;

    [Fact]
    public void NewEntity_InitializesNonEmptyIdAndCreatedAt()
    {
        var entity = new TestEntity();

        Assert.NotEqual(Guid.Empty, entity.Id);
        Assert.Null(entity.UpdatedAtUtc);
    }

    [Fact]
    public void TouchUpdatedAt_SetsUpdatedTimestamp()
    {
        var entity = new TestEntity();
        var now = new DateTime(2026, 11, 26, 17, 0, 0, DateTimeKind.Utc);

        entity.TouchUpdatedAt(now);

        Assert.Equal(now, entity.UpdatedAtUtc);
    }
}
