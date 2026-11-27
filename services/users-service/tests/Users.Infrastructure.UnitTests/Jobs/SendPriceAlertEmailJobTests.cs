using Microsoft.Extensions.Logging.Abstractions;
using Users.Application.Common.Interfaces.Email;
using Users.Application.Common.Interfaces.Jobs;
using Users.Infrastructure.Jobs;

namespace Users.Infrastructure.UnitTests.Jobs;

public sealed class SendPriceAlertEmailJobTests
{
    [Fact]
    public async Task ExecuteAsync_BuildsHtmlAndPlainTextAndCallsEmailSender()
    {
        var spySender = new SpyEmailSender();
        var job = new SendPriceAlertEmailJob(spySender, NullLogger<SendPriceAlertEmailJob>.Instance);

        var payload = new PriceAlertEmailJobPayload(
            "buyer@example.com",
            "Sara",
            "en",
            "laptop_tuf",
            "ASUS TUF Gaming F16",
            "PRICE_DROP",
            73500m,
            69999m,
            "2B Egypt",
            true);

        await job.ExecuteAsync(payload);

        var sent = Assert.Single(spySender.SentMessages);
        Assert.Equal("buyer@example.com", sent.ToEmail);
        Assert.Equal("Sara", sent.ToName);
        Assert.Equal("Price Drop: ASUS TUF Gaming F16", sent.Subject);
        Assert.Contains("69,999 EGP", sent.HtmlBody);
        Assert.False(string.IsNullOrWhiteSpace(sent.PlainTextBody));
    }

    private sealed class SpyEmailSender : IEmailSender
    {
        public List<EmailMessage> SentMessages { get; } = [];

        public Task SendAsync(EmailMessage message, CancellationToken cancellationToken = default)
        {
            SentMessages.Add(message);
            return Task.CompletedTask;
        }
    }
}
