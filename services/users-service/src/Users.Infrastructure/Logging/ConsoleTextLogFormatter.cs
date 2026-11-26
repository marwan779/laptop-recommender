using System.Globalization;
using System.Text;
using Microsoft.Extensions.Logging;

namespace Users.Infrastructure.Logging;

/// <summary>
/// Human-readable single-line console formatter for local development.
/// </summary>
public static class ConsoleTextLogFormatter
{
    public static string Format(
        DateTime timestampUtc,
        LogLevel level,
        string message,
        LoggerConfig config,
        string loggerName,
        string? correlationId,
        IReadOnlyDictionary<string, object?>? context,
        Exception? exception)
    {
        var builder = new StringBuilder(160);
        builder.Append(timestampUtc.ToLocalTime().ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture));
        builder.Append(' ');
        builder.Append(ToLevelText(level));
        builder.Append(' ');
        builder.Append(loggerName);

        if (!string.IsNullOrWhiteSpace(correlationId))
        {
            builder.Append(" [cid=").Append(correlationId).Append(']');
        }

        builder.Append(": ").Append(message);

        if (context is { Count: > 0 })
        {
            foreach (var entry in context)
            {
                builder.Append(' ').Append(entry.Key).Append('=').Append(FormatValue(entry.Value));
            }
        }

        if (exception is not null)
        {
            builder.AppendLine();
            builder.Append(exception);
        }

        return builder.ToString();
    }

    private static string ToLevelText(LogLevel level) => level switch
    {
        LogLevel.Trace or LogLevel.Debug => "DEBUG",
        LogLevel.Information => "INFO",
        LogLevel.Warning => "WARN",
        LogLevel.Error => "ERROR",
        LogLevel.Critical => "CRITICAL",
        _ => "INFO",
    };

    private static string FormatValue(object? value)
    {
        return value switch
        {
            null => "null",
            string text => text,
            DateTime dateTime => dateTime.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture),
            IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
            _ => value.ToString() ?? string.Empty,
        };
    }
}
