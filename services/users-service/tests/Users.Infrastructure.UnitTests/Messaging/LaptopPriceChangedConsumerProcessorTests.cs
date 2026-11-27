using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Messaging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Features.Notifications.Events;
using Users.Domain.Entities;
using Users.Infrastructure.Logging;
using Users.Infrastructure.Messaging;

namespace Users.Infrastructure.UnitTests.Messaging;

public sealed class LaptopPriceChangedConsumerProcessorTests
{
    [Fact]
    public async Task ProcessAsync_ValidSnakeCaseMessage_CallsHandlerAndStoresInboxEntry()
    {
        var inbox = new FakeInboxRepository();
        var handler = new SpyHandler();
        var uow = new FakeUnitOfWork();
        var processor = CreateProcessor(inbox, handler, uow);

        const string payload = """
            {
              "event_id": "msg-001",
              "event_type": "laptop.price.changed.event",
              "timestamp": "2026-11-27T08:00:00Z",
              "correlation_id": "corr-123",
              "payload": {
                "batch_id": "batch-001",
                "store_key": "twob",
                "changes": [
                  {
                    "canonical_id": "laptop_asus_tuf_gaming_fx607vurl167w",
                    "title": "ASUS TUF Gaming F16",
                    "old_price_egp": 73500.0,
                    "new_price_egp": 69999.0,
                    "cheapest_store": "2B Egypt",
                    "in_stock": true,
                    "change_type": "PRICE_DROP"
                  }
                ]
              }
            }
            """;

        var outcome = await processor.ProcessAsync(
            "msg-001",
            "laptop.price.changed.event",
            payload,
            "corr-123");

        Assert.Equal(MessageProcessOutcome.Ack, outcome);
        Assert.Equal(1, handler.CallCount);
        var change = Assert.Single(handler.LastEvent!.Payload.Changes);
        Assert.Equal("laptop_asus_tuf_gaming_fx607vurl167w", change.CanonicalId);
        Assert.Equal(69999.0m, change.NewPriceEgp);
        Assert.Single(inbox.Items);
        Assert.Equal(1, uow.SaveCount);
    }

    [Fact]
    public async Task ProcessAsync_DuplicateMessageId_SkipsHandlerAndAcks()
    {
        var inbox = new FakeInboxRepository();
        await inbox.AddAsync(InboxMessage.Create("msg-dup", "laptop.price.changed.event", DateTime.UtcNow));
        var handler = new SpyHandler();
        var uow = new FakeUnitOfWork();
        var processor = CreateProcessor(inbox, handler, uow);

        const string payload = """
            {"event_id":"msg-dup","event_type":"laptop.price.changed.event","payload":{"batch_id":"b1","changes":[{"canonical_id":"laptop_1","title":"Test","cheapest_store":"sigma","in_stock":true,"change_type":"PRICE_DROP"}]}}
            """;

        var outcome = await processor.ProcessAsync("msg-dup", "laptop.price.changed.event", payload, null);

        Assert.Equal(MessageProcessOutcome.Ack, outcome);
        Assert.Equal(0, handler.CallCount);
        Assert.Equal(0, uow.SaveCount);
    }

    [Fact]
    public async Task ProcessAsync_MalformedJson_DeadLettersWithoutCallingHandler()
    {
        var inbox = new FakeInboxRepository();
        var handler = new SpyHandler();
        var uow = new FakeUnitOfWork();
        var processor = CreateProcessor(inbox, handler, uow);

        var outcome = await processor.ProcessAsync("msg-bad", "laptop.price.changed.event", "{not-json", null);

        Assert.Equal(MessageProcessOutcome.DeadLetter, outcome);
        Assert.Equal(0, handler.CallCount);
        Assert.Empty(inbox.Items);
    }

    private static LaptopPriceChangedConsumerProcessor CreateProcessor(
        FakeInboxRepository inbox,
        SpyHandler handler,
        FakeUnitOfWork uow)
    {
        var services = new ServiceCollection();
        services.AddSingleton<IInboxRepository>(inbox);
        services.AddSingleton<IIntegrationEventHandler<LaptopPriceChangedBatchEvent>>(handler);
        services.AddSingleton<IDateTimeProvider>(new FakeClock(new DateTime(2026, 11, 26, 20, 30, 0, DateTimeKind.Utc)));
        services.AddSingleton<IUnitOfWork>(uow);

        var provider = services.BuildServiceProvider();
        return new LaptopPriceChangedConsumerProcessor(
            provider.GetRequiredService<IServiceScopeFactory>(),
            new AsyncLocalLogContextAccessor(),
            NullLogger<LaptopPriceChangedConsumerProcessor>.Instance);
    }

    private sealed class FakeInboxRepository : IInboxRepository
    {
        public List<InboxMessage> Items { get; } = [];
        public Task<bool> ExistsAsync(string messageId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.Any(m => m.MessageId == messageId));
        public Task AddAsync(InboxMessage message, CancellationToken cancellationToken = default)
        {
            Items.Add(message);
            return Task.CompletedTask;
        }
    }

    private sealed class SpyHandler : IIntegrationEventHandler<LaptopPriceChangedBatchEvent>
    {
        public int CallCount { get; private set; }
        public LaptopPriceChangedBatchEvent? LastEvent { get; private set; }
        public Task HandleAsync(LaptopPriceChangedBatchEvent integrationEvent, string messageId, CancellationToken cancellationToken = default)
        {
            CallCount++;
            LastEvent = integrationEvent;
            return Task.CompletedTask;
        }
    }

    private sealed class FakeClock(DateTime utcNow) : IDateTimeProvider
    {
        public DateTime UtcNow { get; } = utcNow;
    }

    private sealed class FakeUnitOfWork : IUnitOfWork
    {
        public int SaveCount { get; private set; }
        public Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
        {
            SaveCount++;
            return Task.FromResult(1);
        }
    }
}
