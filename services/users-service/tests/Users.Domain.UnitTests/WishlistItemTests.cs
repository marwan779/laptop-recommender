using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Domain.UnitTests;

public sealed class WishlistItemTests
{
    [Fact]
    public void Create_TrimsFieldsAndSetsDefaults()
    {
        var userId = Guid.NewGuid();
        var item = WishlistItem.Create(
            userId,
            "  laptop_asus_tuf_gaming_fx607vurl167w  ",
            "  ASUS TUF Gaming F16  ",
            69999m,
            "https://example.com/tuf.jpg",
            65000m);

        Assert.Equal(userId, item.UserId);
        Assert.Equal("laptop_asus_tuf_gaming_fx607vurl167w", item.CanonicalId);
        Assert.Equal("ASUS TUF Gaming F16", item.TitleSnapshot);
        Assert.Equal(69999m, item.AddedPriceEgp);
        Assert.Equal(65000m, item.TargetPriceEgp);
        Assert.True(item.NotifyOnPriceDrop);
        Assert.False(item.NotifyOnAnyChange);
        Assert.True(item.NotifyOnRestock);
    }

    [Fact]
    public void Create_RejectsInvalidTargetPriceOrNegativePrice()
    {
        Assert.Throws<DomainException>(() =>
            WishlistItem.Create(Guid.NewGuid(), "laptop_1", "Title", -1m));

        Assert.Throws<DomainException>(() =>
            WishlistItem.Create(Guid.NewGuid(), "laptop_1", "Title", 50000m, targetPriceEgp: 0m));
    }

    [Fact]
    public void UpdatePreferences_UpdatesFlagsAndTimestamp()
    {
        var item = WishlistItem.Create(Guid.NewGuid(), "laptop_1", "Title", 50000m);
        var now = new DateTime(2026, 11, 26, 20, 0, 0, DateTimeKind.Utc);

        item.UpdatePreferences(45000m, notifyOnPriceDrop: true, notifyOnAnyChange: true, notifyOnRestock: false, now);

        Assert.Equal(45000m, item.TargetPriceEgp);
        Assert.True(item.NotifyOnAnyChange);
        Assert.False(item.NotifyOnRestock);
        Assert.Equal(now, item.UpdatedAtUtc);
    }
}
