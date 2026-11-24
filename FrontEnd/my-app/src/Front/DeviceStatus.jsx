export default function DeviceStatus({ feedback, saving, onRetry }) {
  const status = feedback?.status;
  const failed = status === "error";
  if (!failed && status !== "loading" && status !== "saving") return null;
  return (
    <div className="device-status" role="status" data-error={failed}>
      {(status === "loading" || status === "saving") && saving}
      {failed && (
        <>
          {feedback.error || "Не удалось подтвердить настройку."}
          <button type="button" onClick={onRetry}>
            Повторить
          </button>
        </>
      )}
    </div>
  );
}
