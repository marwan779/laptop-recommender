using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Logging;

namespace Users.Infrastructure.Logging;

public sealed class GlobalLogger : ILogger
{
    private readonly string _categoryName;
    private readonly LoggerConfig _config;
    private readonly ILogContextAccessor _contextAccessor;
    private readonly TextWriter _writer;
    private readonly object _writeLock;

    internal GlobalLogger(
        string categoryName,
        LoggerConfig config,
        ILogContextAccessor contextAccessor,
        TextWriter writer,
        object writeLock)
    {
        _categoryName = categoryName;
        _config = config;
        _contextAccessor = contextAccessor;
        _writer = writer;
        _writeLock = writeLock;
    }

    public IDisposable BeginScope<TState>(TState state) where TState : notnull => NullScope.Instance;

    public bool IsEnabled(LogLevel logLevel)
    {
        if (logLevel == LogLevel.None || logLevel < _config.MinimumLevel)
        {
            return false;
        }

        if (_config.MinimumLevel != LogLevel.Debug
            && logLevel < LogLevel.Warning
            && IsNoisyFrameworkCategory())
        {
            return false;
        }

        return true;
    }

    public void Log<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    {
        if (!IsEnabled(logLevel))
        {
            return;
        }

        var message = formatter(state, exception);
        if (string.IsNullOrEmpty(message) && exception is null)
        {
            return;
        }

        var structuredProperties = ExtractProperties(state);
        var context = MergeContext(_contextAccessor.GetBoundContext(), structuredProperties);
        var correlationId = _contextAccessor.CorrelationId;
        var threadName = Thread.CurrentThread.Name
            ?? $"Thread-{Environment.CurrentManagedThreadId}";
        var timestampUtc = DateTime.UtcNow;

        var line = _config.JsonOutput
            ? DatadogJsonLogFormatter.Format(
                timestampUtc,
                logLevel,
                message,
                _config,
                _categoryName,
                threadName,
                correlationId,
                context,
                exception)
            : ConsoleTextLogFormatter.Format(
                timestampUtc,
                logLevel,
                message,
                _config,
                _categoryName,
                correlationId,
                context,
                exception);

        lock (_writeLock)
        {
            _writer.WriteLine(line);
            _writer.Flush();
        }
    }

    private bool IsNoisyFrameworkCategory() =>
        _categoryName.StartsWith("Microsoft.EntityFrameworkCore", StringComparison.Ordinal)
        || _categoryName.StartsWith("Microsoft.AspNetCore", StringComparison.Ordinal);

    private static Dictionary<string, object?>? ExtractProperties<TState>(TState state)
    {
        if (state is not IEnumerable<KeyValuePair<string, object?>> values)
        {
            return null;
        }

        Dictionary<string, object?>? properties = null;
        foreach (var value in values)
        {
            if (value.Key == "{OriginalFormat}")
            {
                continue;
            }

            properties ??= new Dictionary<string, object?>(StringComparer.Ordinal);
            properties[value.Key] = value.Value;
        }

        return properties;
    }

    private static IReadOnlyDictionary<string, object?>? MergeContext(
        IReadOnlyDictionary<string, object?> boundContext,
        IReadOnlyDictionary<string, object?>? structuredProperties)
    {
        if (boundContext.Count == 0 && structuredProperties is not { Count: > 0 })
        {
            return null;
        }

        var merged = new Dictionary<string, object?>(
            boundContext.Count + (structuredProperties?.Count ?? 0),
            StringComparer.Ordinal);

        foreach (var entry in boundContext)
        {
            merged[entry.Key] = entry.Value;
        }

        if (structuredProperties is not null)
        {
            foreach (var entry in structuredProperties)
            {
                merged[entry.Key] = entry.Value;
            }
        }

        return merged;
    }

    private sealed class NullScope : IDisposable
    {
        public static readonly NullScope Instance = new();

        public void Dispose()
        {
        }
    }
}
