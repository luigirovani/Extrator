# Extrator

## Setup

Before running the program, make sure to set your credentials in environment variables:

<pre>
<strong>Windows</strong>
set api_id=12345678
set api_hash=abcdce12345678

<strong>Linux</strong>
export api_id=12345678
export api_hash=abcdce12345678
</pre>

## Installation

Install the required dependencies using the requirements.txt file:

<pre>
pip install -r requirements.txt
</pre>

## Sessions

Place your account session files in the `sessions` folder.

## Running the Extractor

To run the extractor, execute the following command:

<pre>
python Extrator.py
</pre>

Wait for the code to finish executing.

## Optional Configuration

<pre>
- <strong>keys.txt:</strong> You can add keywords to this file to filter groups. Only groups containing these keywords in their titles will be extracted.
- <strong>blacklist.txt:</strong> You can add keywords to this file to exclude groups. Groups containing these keywords in their titles will be ignored.
</pre>
