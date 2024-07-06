from datetime import datetime
from time import sleep
from getpass import getpass
import argparse
import json

from selenium.common import NoSuchElementException, TimeoutException
from undetected_chromedriver import Chrome
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

SLEEP_TIME = 1
URL = "https://www.cvs.com/retail-easy-account/create-account?returnUrl=/extracare/new-card/&icid=ec-home-41000-sign-in"
class SlowChrome(Chrome):
    def __init__(self, *args, **kwargs):
        super(SlowChrome, self).__init__(*args, **kwargs)

    def __getattribute__(self, item):
        if item in ["get", "find_element"]:
            sleep(SLEEP_TIME)
        return super(SlowChrome, self).__getattribute__(item)

class CVSCouponGrabber:
    def __init__(self, cmd_args):
        if cmd_args.no_prompt is None:
            self.email = input("Enter your email: ")
            self.password = getpass("Enter your password: ")

        else:
            self.email = args.no_prompt[0]
            self.password = args.no_prompt[1]

        options = ChromeOptions()
        # options.add_argument("--headless")
        self.driver = SlowChrome(options=options)

    def main(self):
        self.driver.get(URL)

        # Apply cookies
        with open('CVSCookies.json', 'r') as f:
            cookies = json.load(f)
        for cookie in cookies:
            self.driver.add_cookie({
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie['domain']
            })

        # Dismiss survey modal if present
        try:
            self.wait_until_visible_by_locator((By.XPATH, "//button[contains(text(), 'Not Now')]")).click()
        except (NoSuchElementException, TimeoutException):
            pass

        # Enter email (content within shadow DOM)
        try:
            shadow_host = self.wait_until_visible_by_locator((By.XPATH, "//cvs-email-lookup"))
            shadow_root = self.get_shadow_root(shadow_host)
            email_input = self.wait_until_visible_by_locator((By.ID, "cvs-form-0-input-email"), driver=shadow_root)
            email_input.click()
            email_input.send_keys(self.email + Keys.ENTER)
            self.email = None
        except (NoSuchElementException, TimeoutException):
            self.driver.save_screenshot("error_screenshot.png")
            with open("page_source.html", "w") as f:
                f.write(self.driver.page_source)
            raise 

        # Scroll to bottom to load all dynamic content
        sleep(30)
        self.wait_until_visible_by_locator((By.XPATH, "//cvs-coupon-container"))
        self.scroll_to_bottom_of_dynamic_webpage()

        # Print coupon info
        all_coupon_elems = self.driver.find_elements(By.XPATH, "//cvs-coupon-container")
        sent_coupon_elems = self.driver.find_elements(
            By.XPATH, "//cvs-coupon-container[.//send-to-card-action/on-card]"
        )
        unsent_coupon_elems = self.driver.find_elements(
            By.XPATH, "//cvs-coupon-container[.//send-to-card-action/button]"
        )
        print("Already on card: {}/{}".format(len(sent_coupon_elems), len(all_coupon_elems)))
        self.print_coupons(sent_coupon_elems)
        print("Not on card: {}/{}".format(len(unsent_coupon_elems), len(all_coupon_elems)))
        self.print_coupons(unsent_coupon_elems)
        print()

        # Send all to card
        self.send_coupons_to_card(unsent_coupon_elems)

    def wait_until_visible_by_locator(self, locator, driver=None, timeout=10):
        if driver is None:
            driver = self.driver
        return WebDriverWait(driver, timeout).until(ec.visibility_of_element_located(locator))

    def wait_until_present_by_locator(self, locator, driver=None, timeout=10):
        if driver is None:
            driver = self.driver
        return WebDriverWait(driver, timeout).until(ec.presence_of_element_located(locator))

    def scroll_to_bottom_of_dynamic_webpage(self, content_load_wait=0.1, timeout=30):
        last_height = None
        new_height = self.get_scroll_height()
        start_time = datetime.now()
        while new_height != last_height:
            if (datetime.now() - start_time).total_seconds() > timeout:
                raise TimeoutError("Timed out trying to scroll to bottom of dynamic webpage.")
            self.scroll_to_bottom()
            sleep(content_load_wait)
            last_height = new_height
            new_height = self.get_scroll_height()

    def get_shadow_root(self, element):
        shadow_root = self.driver.execute_script('return arguments[0].shadowRoot', element)
        return shadow_root

    def find_element_in_shadow_root(self, shadow_root, selector):
        # Print all elements within the shadow root for debugging purposes
        all_elements = shadow_root.find_elements(By.CSS_SELECTOR, "*")
        print(f"Elements within shadow root for selector '{selector}':")
        for elem in all_elements:
            print(f"Tag: {elem.tag_name}, Text: {elem.text}, Attributes: {self.get_element_attributes(elem)}")
        
        # Find the specific element by selector
        return shadow_root.find_element(By.CSS_SELECTOR, selector)
    
    def get_element_attributes(self, element):
        attributes = {}
        for attr in element.get_property('attributes'):
            attributes[attr['name']] = attr['value']
        return attributes
    
    def get_scroll_height(self):
        return self.driver.execute_script("return document.body.scrollHeight")

    def scroll_to_bottom(self):
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def print_coupons(self, coupon_elems):
        for index, elem in enumerate(coupon_elems):
            title = elem.find_element(By.XPATH, ".//*[contains(@class, 'coupon-title')]").text
            sub_heading = elem.find_element(By.XPATH, ".//div[contains(@class, 'coupon-sub-heading')]").text
            details = elem.find_element(By.XPATH, ".//div[contains(@class, 'coupon-details')]").text
            exp_date = (
                elem.find_element(By.XPATH, ".//div[contains(@class, 'coupon-exp-date')]")
                .text.lower()
                .lstrip("exp ")
                .rstrip("mfr")
            )

            print(
                "    {number}. {title}{sub_heading}\n"
                "        Details: {details}\n"
                "        Expires: {exp_date}".format(
                    number=index + 1,
                    title=title,
                    sub_heading=": " + sub_heading if sub_heading != "" else "",
                    details=details,
                    exp_date=exp_date,
                )
            )

    def send_coupons_to_card(self, coupon_elems):
        total_num = len(coupon_elems)
        for index, elem in enumerate(coupon_elems):
            print("Sending {}/{}...".format(index + 1, total_num))
            elem.find_element(By.XPATH, ".//send-to-card-action/button").click()
            self.wait_until_visible_by_locator((By.XPATH, ".//send-to-card-action/on-card"), driver=elem)
        print("All coupons sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--no-prompt", action="store", nargs=3)
    args = parser.parse_args()

    grabber = CVSCouponGrabber(cmd_args=args)
    try:
        grabber.main()
    finally:
        grabber.driver.quit()