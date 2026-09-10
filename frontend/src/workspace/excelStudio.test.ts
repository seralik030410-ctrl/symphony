import { describe, it, expect } from "vitest";
import { getExcelColLetter } from "./OfficeStudio";

describe("Excel Studio helper functions", () => {
  it("converts single column indices to standard letters (A..Z)", () => {
    expect(getExcelColLetter(0)).toBe("A");
    expect(getExcelColLetter(1)).toBe("B");
    expect(getExcelColLetter(2)).toBe("C");
    expect(getExcelColLetter(25)).toBe("Z");
  });

  it("converts two-letter column indices (AA..ZZ)", () => {
    expect(getExcelColLetter(26)).toBe("AA");
    expect(getExcelColLetter(27)).toBe("AB");
    expect(getExcelColLetter(51)).toBe("AZ");
    expect(getExcelColLetter(52)).toBe("BA");
    expect(getExcelColLetter(701)).toBe("ZZ");
  });

  it("converts three-letter column indices (AAA)", () => {
    expect(getExcelColLetter(702)).toBe("AAA");
  });

  it("generates correct formula strings for quick functions", () => {
    const colLetter = getExcelColLetter(1); // 'B'
    const startRow = 2;
    const endRow = 10;
    const formulaSum = `=SUM(${colLetter}${startRow}:${colLetter}${endRow})`;
    const formulaAvg = `=AVERAGE(${colLetter}${startRow}:${colLetter}${endRow})`;

    expect(formulaSum).toBe("=SUM(B2:B10)");
    expect(formulaAvg).toBe("=AVERAGE(B2:B10)");
  });
});
