using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Features.Notifications.Email;

namespace Users.Application.UnitTests.Features.Notifications;

public sealed class EmailBodyBuilderTests
{
    [Fact]
    public void BuildPriceAlertHtml_EnglishPriceDrop_RendersLtrHtmlWithSavingsAndEscaping()
    {
        var payload = new PriceAlertEmailJobPayload(
            "user@example.com",
            "Omar <Admin>",
            "en",
            "laptop_asus_tuf",
            "ASUS TUF Gaming F16",
            "PRICE_DROP",
            73500m,
            69999m,
            "2B Egypt",
            true);

        var subject = EmailBodyBuilder.BuildPriceAlertSubject(payload);
        var html = EmailBodyBuilder.BuildPriceAlertHtml(payload);
        var plain = EmailBodyBuilder.BuildPriceAlertPlainText(payload);

        Assert.Equal("Price Drop: ASUS TUF Gaming F16", subject);
        Assert.Contains("dir=\"ltr\"", html);
        Assert.Contains("PRICE DROP", html);
        Assert.Contains("69,999 EGP", html);
        Assert.Contains("73,500 EGP", html);
        Assert.Contains("2B Egypt", html);
        Assert.Contains("Omar &lt;Admin&gt;", html);
        Assert.DoesNotContain("Omar <Admin>", html);
        Assert.Contains("SAVE 3,501 EGP", html);
        Assert.Contains("69,999 EGP", plain);
    }

    [Fact]
    public void BuildPriceAlertHtml_ArabicRestock_RendersRtlHtml()
    {
        var payload = new PriceAlertEmailJobPayload(
            "user@example.com",
            "أحمد",
            "ar",
            "laptop_legion_5",
            "Lenovo Legion 5",
            "RESTOCK",
            80000m,
            80000m,
            "B.TECH",
            true);

        var subject = EmailBodyBuilder.BuildPriceAlertSubject(payload);
        var html = EmailBodyBuilder.BuildPriceAlertHtml(payload);

        Assert.StartsWith("متوفر الآن:", subject);
        Assert.Contains("dir=\"rtl\"", html);
        Assert.Contains("lang=\"ar\"", html);
        Assert.Contains("متوفر مجدداً", html);
    }
}
