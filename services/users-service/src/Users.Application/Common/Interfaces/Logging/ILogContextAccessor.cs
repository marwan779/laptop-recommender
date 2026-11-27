namespace Users.Application.Common.Interfaces.Logging;

/// <summary>
/// Ambient request/log context supplied by the hosting layer and consumed by
/// infrastructure logging. Application code only depends on this port.
/// </summary>
public interface ILogContextAccessor
{
    string? CorrelationId { get; }

    IDisposable BeginScope(
        string? correlationId,
        IReadOnlyDictionary<string, object?>? properties = null);

    IReadOnlyDictionary<string, object?> GetBoundContext();

    void Clear();
}
