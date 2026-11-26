using System.Text;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using RabbitMQ.Client;
using RabbitMQ.Client.Events;

namespace Users.Infrastructure.Messaging;

public sealed class RabbitMqConsumerBackgroundService(
    IOptions<RabbitMqOptions> options,
    LaptopPriceChangedConsumerProcessor processor,
    ILogger<RabbitMqConsumerBackgroundService> logger) : BackgroundService
{
    private readonly RabbitMqOptions _options = options.Value;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.Enabled)
        {
            logger.LogInformation("RabbitMQ consumer is disabled via configuration.");
            return;
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await RunConsumerLoopAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                logger.LogWarning(
                    ex,
                    "RabbitMQ consumer disconnected or failed to connect to {Host}:{Port}. Retrying in 5s...",
                    _options.HostName,
                    _options.Port);

                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    break;
                }
            }
        }
    }

    private async Task RunConsumerLoopAsync(CancellationToken stoppingToken)
    {
        var factory = new ConnectionFactory
        {
            HostName = _options.HostName,
            Port = _options.Port,
            UserName = _options.UserName,
            Password = _options.Password,
            VirtualHost = _options.VirtualHost,
            AutomaticRecoveryEnabled = true,
            NetworkRecoveryInterval = TimeSpan.FromSeconds(5),
        };

        await using var connection = await factory.CreateConnectionAsync(stoppingToken);
        await using var channel = await connection.CreateChannelAsync(cancellationToken: stoppingToken);

        await channel.ExchangeDeclareAsync(
            exchange: _options.DlxExchangeName,
            type: ExchangeType.Topic,
            durable: true,
            autoDelete: false,
            cancellationToken: stoppingToken);

        await channel.ExchangeDeclareAsync(
            exchange: _options.ExchangeName,
            type: ExchangeType.Topic,
            durable: true,
            autoDelete: false,
            cancellationToken: stoppingToken);

        await channel.QueueDeclareAsync(
            queue: _options.DlqName,
            durable: true,
            exclusive: false,
            autoDelete: false,
            cancellationToken: stoppingToken);

        var dlqRoutingKey = $"dlq.{_options.QueueName}";
        await channel.QueueBindAsync(
            queue: _options.DlqName,
            exchange: _options.DlxExchangeName,
            routingKey: dlqRoutingKey,
            cancellationToken: stoppingToken);

        var queueArgs = new Dictionary<string, object?>
        {
            ["x-dead-letter-exchange"] = _options.DlxExchangeName,
            ["x-dead-letter-routing-key"] = dlqRoutingKey,
        };

        await channel.QueueDeclareAsync(
            queue: _options.QueueName,
            durable: true,
            exclusive: false,
            autoDelete: false,
            arguments: queueArgs,
            cancellationToken: stoppingToken);

        await channel.QueueBindAsync(
            queue: _options.QueueName,
            exchange: _options.ExchangeName,
            routingKey: _options.RoutingKey,
            cancellationToken: stoppingToken);

        await channel.BasicQosAsync(0, _options.PrefetchCount, false, stoppingToken);

        logger.LogInformation(
            "RabbitMQ consumer listening on queue '{Queue}' (exchange='{Exchange}', routingKey='{RoutingKey}')",
            _options.QueueName,
            _options.ExchangeName,
            _options.RoutingKey);

        var consumer = new AsyncEventingBasicConsumer(channel);
        consumer.ReceivedAsync += async (_, ea) =>
        {
            var messageId = ea.BasicProperties.MessageId ?? string.Empty;
            var correlationId = ea.BasicProperties.CorrelationId;
            var payload = Encoding.UTF8.GetString(ea.Body.Span);

            try
            {
                var outcome = await processor.ProcessAsync(
                    messageId,
                    ea.RoutingKey,
                    payload,
                    correlationId,
                    stoppingToken);

                switch (outcome)
                {
                    case MessageProcessOutcome.Ack:
                        await channel.BasicAckAsync(ea.DeliveryTag, multiple: false, stoppingToken);
                        break;
                    case MessageProcessOutcome.DeadLetter:
                        await channel.BasicNackAsync(ea.DeliveryTag, multiple: false, requeue: false, stoppingToken);
                        break;
                    default:
                        await channel.BasicNackAsync(ea.DeliveryTag, multiple: false, requeue: true, stoppingToken);
                        break;
                }
            }
            catch (Exception ex)
            {
                logger.LogError(
                    ex,
                    "Unhandled error processing RabbitMQ message [messageId={MessageId}, deliveryTag={DeliveryTag}]",
                    messageId,
                    ea.DeliveryTag);
                await channel.BasicNackAsync(ea.DeliveryTag, multiple: false, requeue: true, stoppingToken);
            }
        };

        await channel.BasicConsumeAsync(
            queue: _options.QueueName,
            autoAck: false,
            consumer: consumer,
            cancellationToken: stoppingToken);

        await Task.Delay(Timeout.Infinite, stoppingToken);
    }
}
