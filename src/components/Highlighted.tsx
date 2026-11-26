import React from 'react';
import { BRAND, highlightWords } from '../brand';

export const Highlighted: React.FC<{ text: string; highlight?: string | string[] }> = ({ text, highlight }) => (
  <>
    {highlightWords(text, highlight).map((p, i) => (
      <span key={i} style={p.hl ? { color: BRAND.accent } : undefined}>
        {p.text}
      </span>
    ))}
  </>
);
