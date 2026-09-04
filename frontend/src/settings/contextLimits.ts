export function contextOptions(current: number, maximum: number | null): number[] {
  const presets = [8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576];
  const values = [...presets, current];
  if (maximum !== null && !presets.includes(maximum)) values.push(maximum);
  const unique = [...new Set(values)].sort((a, b) => a - b);
  // Keep only values that make sense: at most the model maximum (if known)
  return unique;
}

export function validContextBudget(windowSize: number, output: string, maximum: number | null): boolean {
  const count = Number(output);
  return maximum !== null && Number.isInteger(windowSize) && windowSize >= 1024 && windowSize <= maximum
    && Number.isInteger(count) && count >= 64 && count < windowSize;
}
