from bs4 import BeautifulSoup
import re
from collections import Counter
from typing import List, Tuple, Dict
import sys,os


class HTMLROUGEScorer:
    """
    A class to calculate ROUGE-5 scores between HTML documents.
    """

    def calculate_html_rouge_5_diff(self, html1: str, html2: str) -> float:
        """
        Calculate the ROUGE-5 score between two HTML strings.

        Args:
            html1 (str): First HTML string
            html2 (str): Second HTML string

        Returns:
            float: ROUGE-5 F1-score (between 0 and 1)
        """
        # Extract text content from HTML
        text1 = self.extract_text_from_html(html1)
        text2 = self.extract_text_from_html(html2)

        # Tokenize into n-grams
        ngrams1 = self.get_5grams(text1)
        ngrams2 = self.get_5grams(text2)

        # Calculate ROUGE-5
        return self.rouge_n_score(ngrams1, ngrams2, n=5)

    def extract_text_from_html(self, html: str) -> str:
        """
        Extract clean text content from HTML string.

        Args:
            html (str): HTML string

        Returns:
            str: Cleaned text content
        """
        # Parse HTML and extract text
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text.lower()

    def get_5grams(self, text: str) -> List[Tuple[str, ...]]:
        """
        Generate 5-grams from text.

        Args:
            text (str): Input text

        Returns:
            List[Tuple[str, ...]]: List of 5-gram tuples
        """
        # Simple tokenization by whitespace
        tokens = text.split()

        # Generate 5-grams
        ngrams = []
        for i in range(len(tokens) - 4):
            ngrams.append(tuple(tokens[i:i+5]))

        return ngrams

    def rouge_n_score(self, ngrams1: List[Tuple[str, ...]], ngrams2: List[Tuple[str, ...]], n: int) -> float:
        """
        Calculate ROUGE-N F1-score.

        Args:
            ngrams1: N-grams from first text
            ngrams2: N-grams from second text
            n: N-gram size

        Returns:
            float: F1-score
        """
        if not ngrams1 and not ngrams2:
            return 1.0
        if not ngrams1 or not ngrams2:
            return 0.0

        # Count n-grams
        count1 = Counter(ngrams1)
        count2 = Counter(ngrams2)

        # Calculate matches
        matches = sum((count1 & count2).values())

        # Calculate precision and recall
        precision = matches / len(ngrams1) if len(ngrams1) > 0 else 0
        recall = matches / len(ngrams2) if len(ngrams2) > 0 else 0

        # Calculate F1-score
        if precision + recall == 0:
            return 0.0

        f1 = 2 * precision * recall / (precision + recall)
        return f1

    def html_rouge_5_diff(self, html1: str, html2: str) -> Dict[str, float]:
        """
        Calculate detailed ROUGE-5 metrics between two HTML strings.

        Args:
            html1 (str): First HTML string
            html2 (str): Second HTML string

        Returns:
            dict: Dictionary containing precision, recall, and F1-score
        """
        # Extract text content from HTML
        # text1 = self.extract_text_from_html(html1)
        # text2 = self.extract_text_from_html(html2)
        text1 = html1
        text2 = html2
        # Tokenize into 5-grams
        ngrams1 = self.get_5grams(text1)
        ngrams2 = self.get_5grams(text2)

        if not ngrams1 and not ngrams2:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        if not ngrams1 or not ngrams2:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

        # Count n-grams
        count1 = Counter(ngrams1)
        count2 = Counter(ngrams2)

        # Calculate matches
        matches = sum((count1 & count2).values())

        # Calculate precision and recall
        precision = matches / len(ngrams1) if len(ngrams1) > 0 else 0
        recall = matches / len(ngrams2) if len(ngrams2) > 0 else 0

        # Calculate F1-score
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1
        }

    def compare_html_files(self, file_path1: str, file_path2: str) -> Dict[str, float]:
        """
        Compare two HTML files and return ROUGE-5 metrics.

        Args:
            file_path1 (str): Path to the first HTML file
            file_path2 (str): Path to the second HTML file

        Returns:
            dict: Dictionary containing precision, recall, and F1-score
        """
        try:
            with open(file_path1, 'r', encoding='utf-8') as f1:
                html1 = f1.read()

            with open(file_path2, 'r', encoding='utf-8') as f2:
                html2 = f2.read()

            return self.html_rouge_5_diff(html1, html2)
        except FileNotFoundError as e:
            print(f"Error: File not found - {e}")
            return {"error": "File not found"}
        except Exception as e:
            print(f"Error reading files: {e}")
            return {"error": "Error processing files"}


    def compare_folders(self, folder1: str, folder2: str, max_files: int = 300) -> List[Dict[str, any]]:
        """
        Compare HTML files between two folders for files with pattern {idx}_{suffix}.html

        Args:
            folder1 (str): Path to the first folder
            folder2 (str): Path to the second folder
            max_files (int): Maximum number of files to compare (default: 300)

        Returns:
            List[Dict]: List of dictionaries containing comparison results for each file
        """
        results = []

        for idx in range(1, max_files + 1):
            file_path = os.path.join("./raw", f"{idx}.html")
            file1_path = os.path.join(folder1, f"{idx}.html")
            file2_path = os.path.join(folder2, f"{idx}.html")

            try:
                result = self.compare_html_files(file1_path, file2_path)
                result["file_index"] = idx
                result["orig"] = file_path
                result["file1"] = file1_path
                result["file2"] = file2_path
                results.append(result)
            except Exception as e:
                results.append({
                    "file_index": idx,
                    "error": str(e),
                    "orig": file_path,
                    "file1": file1_path,
                    "file2": file2_path
                })

        return results

def main():
    """
    Main function to run the HTML comparison.
    """
    # if len(sys.argv) != 3:
    #     print("Usage: python html_rouge_5_diff.py <file1.html> <file2.html>")
    #     sys.exit(1)

    # file_path1 = sys.argv[1]
    # file_path2 = sys.argv[2]
    file_path1 = "app/example.html"
    file_path2 = "app/example2.html"

    scorer = HTMLROUGEScorer()
    result = scorer.compare_html_files(file_path1, file_path2)

    if "error" in result:
        sys.exit(1)

    print(f"Comparison results for {file_path1} and {file_path2}:")
    print(f"Precision: {result['precision']:.4f}")
    print(f"Recall: {result['recall']:.4f}")
    print(f"F1-Score: {result['f1']:.4f}")

def compare_result_folders():
    """
    Compare ./result0 and ./result folders for files 1 to 300
    """
    scorer = HTMLROUGEScorer()
    results = scorer.compare_folders("./results0", "./results", 1000)

    # Print results in a tabular format
    print(f"{'Index':<6} {'File1':<15} {'File2':<15} {'Precision':<10} {'Recall':<10} {'F1-Score':<10}")
    print("-" * 70)

    for result in results:
        if "error" not in result:
            print(f"{result['file_index']:<6} {result['file1']:<15} {result['file2']:<15} "
                    f"{result['precision']:<10.4f} {result['recall']:<10.4f} {result['f1']:<10.4f}")
        else:
            print(f"{result['file_index']:<6} {result['file1']:<15} {result['file2']:<15} "
                    f"{'ERROR':<10} {'ERROR':<10} {'ERROR':<10} - {result['error']}")


def compare_result_foldersEx():
    """
    Compare ./result0 and ./result folders for files 1 to 300 and calculate high similarity ratio
    """
    scorer = HTMLROUGEScorer()
    results = scorer.compare_folders("./results0", "./resultsOpt", 1000)

    # Print results in a tabular format
    print(f"{'Index':<6} {'orig':<15} {'File1':<15} {'File2':<15} {'Precision':<10} {'Recall':<10} {'F1-Score':<10}")
    print("-" * 70)

    # Counters for high similarity files
    high_precision_count = 0
    high_recall_count = 0
    high_both_count = 0
    total_valid_files = 0
    perfect_match_count = 0

    # List to store low similarity records
    low_similarity_records = []

    for result in results:
        if "error" not in result:
            total_valid_files += 1
            precision = result['precision']
            recall = result['recall']
            f1 = result['f1']

            # Count files with high precision/recall
            if precision > 0.9:
                high_precision_count += 1
            if recall > 0.9:
                high_recall_count += 1
            if precision > 0.9 and recall > 0.9:
                high_both_count += 1
            if precision == 1.0 and recall == 1.0:
                perfect_match_count += 1

            # Record files with low precision or recall (< 0.5)
            if precision < 0.5 or recall < 0.5:
                low_similarity_records.append({
                    'index': result['file_index'],
                    'orig': result['orig'],
                    'file1': result['file1'],
                    'file2': result['file2'],
                    'precision': precision,
                    'recall': recall,
                    'f1': f1
                })

            print(f"{result['file_index']:<6} {result['orig']:<15} {result['file1']:<15} {result['file2']:<15} "
                  f"{precision:<10.4f} {recall:<10.4f} {f1:<10.4f}")
        else:
            print(f"{result['file_index']:<6} {result['orig']:<15} {result['file1']:<15} {result['file2']:<15} "
                  f"{'ERROR':<10} {'ERROR':<10} {'ERROR':<10} - {result['error']}")

    # Calculate and print ratios
    if total_valid_files > 0:
        precision_ratio = high_precision_count / total_valid_files
        recall_ratio = high_recall_count / total_valid_files
        both_ratio = high_both_count / total_valid_files
        perfect_match_ratio = perfect_match_count / total_valid_files

        print("\n" + "="*70)
        print("HIGH SIMILARITY RATIOS (>0.9):")
        print("="*70)
        print(f"Files with Precision > 0.9: {high_precision_count}/{total_valid_files} ({precision_ratio:.2%})")
        print(f"Files with Recall > 0.9: {high_recall_count}/{total_valid_files} ({recall_ratio:.2%})")
        print(f"Files with BOTH Precision > 0.9 AND Recall > 0.9: {high_both_count}/{total_valid_files} ({both_ratio:.2%})")
        print(f"Files with PERFECT MATCH (Precision=1.0 AND Recall=1.0): {perfect_match_count}/{total_valid_files} ({perfect_match_ratio:.2%})")

        # Print low similarity records
        if low_similarity_records:
            print("\n" + "="*70)
            print("LOW SIMILARITY RECORDS (Precision < 0.5 OR Recall < 0.5):")
            print("="*70)
            print(f"{'Index':<6} {'orig':<15} {'File1':<15} {'File2':<15} {'Precision':<10} {'Recall':<10} {'F1-Score':<10}")
            print("-" * 70)
            for record in low_similarity_records:
                print(f"{record['index']:<6} {record['orig']:<15} {record['file1']:<15} {record['file2']:<15} "
                      f"{record['precision']:<10.4f} {record['recall']:<10.4f} {record['f1']:<10.4f}")
            print(f"\nTotal low similarity records: {len(low_similarity_records)}")
        else:
            print("\nNo low similarity records found.")
    else:
        print("\nNo valid comparisons were made.")


if __name__ == "__main__":
    compare_result_foldersEx()