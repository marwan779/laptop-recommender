using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Logging;

namespace Users.Infrastructure.Logging;

public sealed class GlobalLoggerProvider : ILoggerProvider
{
    private readonly LoggerConfig _config;
    private readonly ILogContextAccessor _contextAccessor;
    private readonly TextWriter _writer;
    private readonly ConcurrentDictionary<string, GlobalLogger> _loggers = new(StringComparer.Ordinal);
    private readonly object _writeLock = new();

    public GlobalLoggerProvider(LoggerConfig config, ILogContextAccessor contextAccessor)
        : this(config, contextAccessor, Console.Out)
    {
    }

    internal GlobalLoggerProvider(
        LoggerConfig config,
        ILogContextAccessor contextAccessor,
        TextWriter writer)
    {
        _config = config;
        _contextAccessor = contextAccessor;
        _writer = TextWriter.Synchronized(writer);
    }

    public ILogger CreateLogger(string categoryName) =>
        _loggers.GetOrAdd(
            categoryName,
            name => new GlobalLogger(name, _config, _contextAccessor, _writer, _writeLock));

    public void Dispose() => _loggers.Clear();
}
