using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Domain.UnitTests;

public sealed class NotificationTests
{
    [Fact]
    public void Create_WithValidData_SetsPropertiesAndUnread()
    {
        var userId = Guid.NewGuid();

        var notification = Notification.Create(
            userId,
            "  laptop_asus_tuf  ",
            "  Price drop: ASUS TUF  ",
            "  Dropped from 73,500 EGP to 69,999 EGP at 2B Egypt.  ",
            "  PRICE_DROP ",
            73500m,
            69999m,
            " 2B Egypt ");

        Assert.Equal(userId, notification.UserId);
        Assert.Equal("laptop_asus_tuf", notification.CanonicalId);
        Assert.Equal("Price drop: ASUS TUF", notification.Title);
        Assert.Equal("Dropped from 73,500 EGP to 69,999 EGP at 2B Egypt.", notification.Message);
        Assert.Equal("PRICE_DROP", notification.ChangeType);
        Assert.Equal(73500m, notification.OldPriceEgp);
        Assert.Equal(69999m, notification.NewPriceEgp);
        Assert.Equal("2B Egypt", notification.CheapestStore);
        Assert.False(notification.IsRead);
        Assert.Null(notification.ReadAtUtc);
    }

    [Fact]
    public void Create_WithEmptyUserId_ThrowsDomainException()
    {
        Assert.Throws<DomainException>(() =>
            Notification.Create(Guid.Empty, "laptop_1", "Title", "Message", "PRICE_DROP"));
    }

    [Fact]
    public void Create_WithNegativePrice_ThrowsDomainException()
    {
        Assert.Throws<DomainException>(() =>
            Notification.Create(Guid.NewGuid(), "laptop_1", "Title", "Message", "PRICE_DROP", newPriceEgp: -1m));
    }

    [Fact]
    public void MarkAsRead_SetsReadFlagAndTimestamp_AndIsIdempotent()
    {
        var notification = Notification.Create(
            Guid.NewGuid(),
            "laptop_1",
            "Title",
            "Message",
            "PRICE_DROP");

        var firstRead = new DateTime(2026, 11, 26, 21, 0, 0, DateTimeKind.Utc);
        var secondRead = firstRead.AddMinutes(10);

        notification.MarkAsRead(firstRead);
        notification.MarkAsRead(secondRead);

        Assert.True(notification.IsRead);
        Assert.Equal(firstRead, notification.ReadAtUtc);
        Assert.Equal(firstRead, notification.UpdatedAtUtc);
    }
}
