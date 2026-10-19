"""Retired image-repair command; use PPT mapping and provider-independent image sync."""
import logging

def main():
    logging.error('Legacy image repair is retired. Run jobs.ppt_report, then jobs.sync_images_to_r2.')
    raise SystemExit(2)

if __name__ == '__main__':
    main()
