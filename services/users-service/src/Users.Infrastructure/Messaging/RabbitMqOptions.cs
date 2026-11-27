namespace Users.Infrastructure.Messaging;

public sealed class RabbitMqOptions
{
    public const string SectionName = "RabbitMq";

    public bool Enabled { get; set; } = true;
    public string HostName { get; set; } = "localhost";
    public int Port { get; set; } = 5672;
    public string UserName { get; set; } = "guest";
    public string Password { get; set; } = "guest";
    public string VirtualHost { get; set; } = "/";
    public string ExchangeName { get; set; } = "laptop_events";
    public string DlxExchangeName { get; set; } = "laptop_events.dlx";
    public string QueueName { get; set; } = "users.price-alerts.queue";
    public string DlqName { get; set; } = "users.price-alerts.dlq";
    public string RoutingKey { get; set; } = "laptop.price.changed.event";
    public ushort PrefetchCount { get; set; } = 10;
}
