# Publishing checklist

Recommended repository name:

`forge-no-copy-download`

Recommended description:

`Prevent Forge Neo's download button from filling output/images with duplicate copies.`

Suggested topics:

`stable-diffusion`, `forge`, `forge-neo`, `stable-diffusion-webui`,
`extension`, `download`, `gradio`

Before publishing:

1. Replace `YOUR_USERNAME` in `README.md` with your GitHub username.
2. Create the GitHub repository with README / .gitignore / license generation disabled.
3. Upload all files from this folder.
4. Commit message:

   `Initial release v1.0.0`

5. Create tag/release:

   `v1.0.0`

6. Release title:

   `Forge No-Copy Download v1.0.0`

Suggested release notes:

```text
Initial public release.

Keeps Forge Neo's normal download buttons while preventing permanent duplicate
download copies from accumulating in output/images.

Features:
- temporary browser-download files
- automatic temp cleanup
- sequential filename numbering across restarts
- no Forge core-file modifications
```
