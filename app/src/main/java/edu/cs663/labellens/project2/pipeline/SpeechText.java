package edu.cs663.labellens.project2.pipeline;

import java.util.ArrayList;
import java.util.List;

/** Keep long label readings within Android's per-utterance limit. */
public final class SpeechText {
    private SpeechText() { }
    public static List<String> chunks(String text, int limit) {
        if (limit < 2) throw new IllegalArgumentException("Speech chunk limit is too small");
        List<String> result = new ArrayList<>();
        String remaining = text == null ? "" : text.trim();
        while (!remaining.isEmpty()) {
            int end = Math.min(limit, remaining.length());
            if (end < remaining.length()) {
                if (Character.isHighSurrogate(remaining.charAt(end - 1))) end--;
                int space = end;
                while (space > end / 2 && !Character.isWhitespace(remaining.charAt(space - 1))) space--;
                if (space > end / 2) end = space;
            }
            result.add(remaining.substring(0, end).trim());
            remaining = remaining.substring(end).trim();
        }
        return result;
    }
}
