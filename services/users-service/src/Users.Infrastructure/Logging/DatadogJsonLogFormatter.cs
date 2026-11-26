using System.Globalization;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Users.Infrastructure.Logging;

/// <summary>
/// Pure formatter producing one Datadog-compatible JSON object per log line.
/// </summary>
public static class DatadogJsonLogFormatter
{
    public static string Format(
        DateTime timestampUtc,
        LogLevel level,
        string message,
        LoggerConfig config,
        string loggerName,
        string threadName,
        string? correlationId,
        IReadOnlyDictionary<string, object?>? context,
        Exception? exception)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            writer.WriteString("timestamp", FormatTimestamp(timestampUtc));
            writer.WriteString("status", ToStatus(level));
            writer.WriteString("message", message);
            writer.WriteString("service", config.ServiceName);
            writer.WriteString("env", config.Environment);
            writer.WriteString("version", config.Version);

            writer.WriteStartObject("logger");
            writer.WriteString("name", loggerName);
            writer.WriteString("thread_name", threadName);
            writer.WriteEndObject();

            if (!string.IsNullOrWhiteSpace(correlationId))
            {
                writer.WriteString("correlation_id", correlationId);
            }

            if (context is { Count: > 0 })
            {
                writer.WriteStartObject("context");
                foreach (var entry in context)
                {
                    writer.WritePropertyName(entry.Key);
                    WriteValue(writer, entry.Value);
                }

                writer.WriteEndObject();
            }

            if (exception is not null)
            {
                writer.WriteStartObject("error");
                writer.WriteString("kind", exception.GetType().FullName ?? exception.GetType().Name);
                writer.WriteString("message", exception.Message);
                writer.WriteString("stack", exception.StackTrace ?? exception.ToString());
                writer.WriteEndObject();
            }

            writer.WriteEndObject();
        }

        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static string FormatTimestamp(DateTime timestampUtc) =>
        timestampUtc.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture);

    private static string ToStatus(LogLevel level) => level switch
    {
        LogLevel.Trace or LogLevel.Debug => "DEBUG",
        LogLevel.Information => "INFO",
        LogLevel.Warning => "WARNING",
        LogLevel.Error or LogLevel.Critical => "ERROR",
        _ => "INFO",
    };

    private static void WriteValue(Utf8JsonWriter writer, object? value)
    {
        switch (value)
        {
            case null:
                writer.WriteNullValue();
                return;
            case string text:
                writer.WriteStringValue(text);
                return;
            case bool boolean:
                writer.WriteBooleanValue(boolean);
                return;
            case int integer:
                writer.WriteNumberValue(integer);
                return;
            case long longInteger:
                writer.WriteNumberValue(longInteger);
                return;
            case double doubleValue:
                writer.WriteNumberValue(doubleValue);
                return;
            case decimal decimalValue:
                writer.WriteNumberValue(decimalValue);
                return;
            case DateTime dateTime:
                writer.WriteStringValue(dateTime);
                return;
            case Guid guid:
                writer.WriteStringValue(guid);
                return;
        }

        try
        {
            JsonSerializer.Serialize(writer, value, value.GetType());
        }
        catch
        {
            writer.WriteStringValue(value.ToString());
        }
    }
}
