using System.Collections.Immutable;
using Users.Application.Common.Interfaces.Logging;

namespace Users.Infrastructure.Logging;

public sealed class AsyncLocalLogContextAccessor : ILogContextAccessor
{
    private readonly AsyncLocal<string?> _correlationId = new();
    private readonly AsyncLocal<ImmutableDictionary<string, object?>?> _context = new();

    public string? CorrelationId => _correlationId.Value;

    public IDisposable BeginScope(
        string? correlationId,
        IReadOnlyDictionary<string, object?>? properties = null)
    {
        var previousCorrelationId = _correlationId.Value;
        var previousContext = _context.Value;

        _correlationId.Value = correlationId;

        if (properties is { Count: > 0 })
        {
            var builder = (previousContext ?? ImmutableDictionary<string, object?>.Empty).ToBuilder();
            foreach (var property in properties)
            {
                builder[property.Key] = property.Value;
            }

            _context.Value = builder.ToImmutable();
        }
        else if (previousContext is not null)
        {
            _context.Value = previousContext;
        }

        return new Scope(this, previousCorrelationId, previousContext);
    }

    public IReadOnlyDictionary<string, object?> GetBoundContext()
    {
        return _context.Value ?? ImmutableDictionary<string, object?>.Empty;
    }

    public void Clear()
    {
        _correlationId.Value = null;
        _context.Value = null;
    }

    private sealed class Scope(
        AsyncLocalLogContextAccessor accessor,
        string? previousCorrelationId,
        ImmutableDictionary<string, object?>? previousContext) : IDisposable
    {
        private bool _disposed;

        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
            accessor._correlationId.Value = previousCorrelationId;
            accessor._context.Value = previousContext;
        }
    }
}
