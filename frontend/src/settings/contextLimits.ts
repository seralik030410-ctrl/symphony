export function contextOptions(current: number, maximum: number | null): number[] {
  const values = [8192, 16384, 32768, 65536, current];
  if (maximum !== null && maximum < 8192) values.push(maximum);
  return [...new Set(values)].sort((a, b) => a - b);
}

export function validContextBudget(windowSize: number, output: string, maximum: number | null): boolean {
  const count = Number(output);
  return maximum !== null && Number.isInteger(windowSize) && windowSize >= 1024 && windowSize <= maximum
    && Number.isInteger(count) && count >= 64 && count <= 65536 && count < windowSize;
}
