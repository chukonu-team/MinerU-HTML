
from dripper.api import Dripper
from html2text import html2text
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_path', type=str, required=True)
    parser.add_argument('--html_file', type=str, default='./app/example.html')
    parser.add_argument('--output_file', type=str, default='./app/example.md')
    args = parser.parse_args()

    # Read HTML file
    print(f'Reading HTML file from {args.html_file}')
    html_content = open(args.html_file, 'r').read()
    
    # Initialize Dripper with model configuration
    print(f'Initializing Dripper with model configuration from {args.model_path}')
    dripper = Dripper(
        config={
            'model_path': args.model_path,
            'tp': 1,  # Tensor parallel size
            'use_fall_back': True,
            'raise_errors': False,
        }
    )

    # start processing
    print(f'Processing HTML content')
    result = dripper.process(html_content)

    # Access results
    print(f'Result: {result[0].main_html}')
    print(f'HTML2Text: {html2text(result[0].main_html, bodywidth=0)}')
    with open(args.output_file, 'w') as f:
        f.write(html2text(result[0].main_html, bodywidth=0))